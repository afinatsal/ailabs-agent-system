"""Executor — loop eksekusi DETERMINISTIK (state machine, bukan LLM).

get_ready_tasks -> dispatch ke agent -> update status -> (opsional) review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ailabs.agents.registry import AgentRegistry
from ailabs.db.base import Storage
from ailabs.models.agent_result import AgentResult
from ailabs.models.job import Job
from ailabs.models.task import Task, TaskStatus
from ailabs.memory.vector_store import Embedder, retrieve_context
from ailabs.utils import slugify

logger = logging.getLogger(__name__)


@dataclass
class RunReport:
    job: Job
    tasks_done: int = 0
    tasks_failed: int = 0
    revisions: int = 0
    events: list[str] = field(default_factory=list)


class Executor:
    def __init__(
        self,
        storage: Storage,
        registry: AgentRegistry,
        *,
        reviewer_enabled: bool = True,
        max_exec_retries: int = 2,
        max_review_rounds: int = 2,
        embedder: Embedder | None = None,
        skills=None,
        workspace_base: str | Path | None = None,
        on_event=None,
    ):
        self.storage = storage
        self.registry = registry
        self.reviewer_enabled = reviewer_enabled
        self.max_exec_retries = max_exec_retries
        self.max_review_rounds = max_review_rounds
        self.embedder = embedder
        self.skills = skills
        self.workspace_base = Path(workspace_base) if workspace_base else None
        self.on_event = on_event or (lambda *_: None)

    def execute_job(self, job_id: str) -> RunReport:
        job = self.storage.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} tidak ditemukan.")
        self._scope_workspace(job)
        report = RunReport(job=job)
        self._emit("MULAI eksekusi job", job_id)
        self.storage.update_job(job_id, status="running")

        for _ in range(200):  # pengaman infinite loop
            if not self.storage.has_remaining(job_id):
                break
            ready = self.storage.get_ready_tasks(job_id)
            if not ready:
                self._fail_stuck(job_id, report)
                return report
            for task in ready:
                self._run_task(job_id, task, report)

        job = self.storage.get_job(job_id)
        if job is None:
            return report
        if job.status != "failed":
            self._synthesize(job, report)
        return report

    # ---------- langkah inti ----------

    def _scope_workspace(self, job: Job) -> None:
        """Arahkan skill write_file ke folder per-project: workspace/<slug>."""
        if self.skills is None or self.workspace_base is None:
            return
        ws = self.workspace_base / self._slug_for(job)
        self.skills.inject_context(workspace_path=str(ws))
        self._emit(f"workspace project -> {ws}", job.id)

    @staticmethod
    def _slug_for(job: Job) -> str:
        return slugify(job.project) if job.project else f"job-{job.id[:8]}"

    # ---------- memori lessons per project ----------

    def _learnings_path(self, job: Job) -> Path | None:
        if self.workspace_base is None:
            return None
        return self.workspace_base / self._slug_for(job) / "_learnings.md"

    def _collect_evidence(self, job: Job, task: Task, result: AgentResult) -> str:
        """Kumpulkan isi file yang ditulis agent sebagai bukti untuk reviewer.

        Mengatasi masalah "reviewer tidak bisa memverifikasi kode": Vera kini
        melihat isi file dari workspace, bukan hanya narasi teks agent.
        """
        if self.workspace_base is None:
            return ""
        ws = self.workspace_base / self._slug_for(job)
        output = result.output or {}

        written: list[str] = []
        files_written = output.get("files_written") or []
        written.extend(files_written)
        agentic = output.get("agentic_loop_result") or {}
        if isinstance(agentic, dict):
            written.extend(agentic.get("files_written") or [])
        opencode = output.get("opencode_result") or {}
        if isinstance(opencode, dict):
            written.extend(opencode.get("files_written") or [])

        parts: list[str] = []
        seen: set[str] = set()
        for raw in written:
            if not raw:
                continue
            path = Path(str(raw))
            if not path.is_absolute():
                path = ws / path
            try:
                path = path.resolve()
            except OSError:
                continue
            if not str(path).startswith(str(ws.resolve())) or path in seen:
                continue
            seen.add(path)
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                parts.append(
                    f"### {path.relative_to(ws)}\n```\n{content[:4000]}\n```"
                )
        return "\n\n".join(parts)

    def _project_snapshot(self, job: Job, max_chars: int = 2500) -> str:
        """Daftar isi workspace project sebagai konteks untuk agent.

        Ini kunci "agent seperti opencode": sebelum bekerja, agent TAHU file
        apa saja yang sudah ada (path + ukuran + cuplikan kecil), sehingga
        tidak menebak/duplikat dan bisa memutuskan file mana yang harus dibaca
        lewat read_file.
        """
        if self.workspace_base is None:
            return ""
        base = self.workspace_base / self._slug_for(job)
        if not base.exists():
            return "(workspace project masih kosong — belum ada file)"
        ignore = {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            ".next", "dist", "build", "vendor",
        }
        lines: list[str] = []
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if any(part in ignore for part in p.relative_to(base).parts):
                continue
            rel = p.relative_to(base)
            size = p.stat().st_size
            lines.append(f"- {rel} ({size} B)")
        if not lines:
            return "(workspace project kosong — belum ada file)"
        return "DAFTAR FILE DI WORKSPACE (untuk tahu apa yang sudah ada — baca file relevan dengan read_file, JANGAN menebak atau menulis ulang dari nol):\n" + "\n".join(lines)[:max_chars]

    def _project_status_path(self, job: Job) -> Path | None:
        if self.workspace_base is None:
            return None
        return self.workspace_base / self._slug_for(job) / "docs" / "PROJECT_STATUS.md"

    def _load_project_status(self, job: Job) -> str:
        """Baca PROJECT_STATUS.md — komunikasi antar agent.

        Setiap worker selesai mencatat file yang dibuat/diperbaiki + status,
        sehingga worker berikutnya tahu kondisi nyata project tanpa perlu
        menebak atau mengulang dari nol.
        """
        path = self._project_status_path(job)
        if path is None or not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8")[:4000]
        except OSError as exc:  # noqa: BLE001
            logger.warning("Gagal membaca PROJECT_STATUS.md: %s", exc)
            return ""
        return "STATUS PROYEK (dibuat agent sebelumnya — baca dulu, lalu lanjutkan):\n" + content

    def _update_project_status(self, job: Job, task: Task, result: AgentResult) -> None:
        """Catat hasil task ke PROJECT_STATUS.md agar agent berikutnya tahu."""
        path = self._project_status_path(job)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            files = (result.output or {}).get("files_written") or []
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            lines = [
                f"\n## {stamp} — {task.agent_name}",
                f"- Task: {task.description}",
                "- Status: selesai",
            ]
            if files:
                lines.append("- File: " + ", ".join(str(f).split("/")[-1] for f in files))
            text = (result.text or "")[:300].strip().replace("\n", " ")
            if text:
                lines.append(f"- Ringkasan: {text}")
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError as exc:  # noqa: BLE001
            logger.warning("Gagal menulis PROJECT_STATUS.md: %s", exc)

    def _append_lesson(self, job: Job, task: Task, feedback: str) -> None:
        path = self._learnings_path(job)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            block = (
                f"\n## {stamp} — {task.agent_name}\n"
                f"- Task: {task.description}\n"
                f"- Reviewer: {feedback}\n"
            )
            with path.open("a", encoding="utf-8") as fh:
                fh.write(block)
        except OSError as exc:  # noqa: BLE001
            logger.warning("Gagal menulis memori lessons: %s", exc)

    def _load_learnings(self, job: Job, agent_name: str) -> str:
        """Baca lessons yang relevan untuk agent dari memori project."""
        path = self._learnings_path(job)
        if path is None or not path.exists():
            return ""
        try:
            blocks = path.read_text(encoding="utf-8").split("\n## ")
        except OSError as exc:  # noqa: BLE001
            logger.warning("Gagal membaca memori lessons: %s", exc)
            return ""
        relevant = [
            b for b in blocks if f"— {agent_name}\n" in b
        ]
        if not relevant:
            return ""
        header = "PEMBELAJARAN SEBELUMNYA (memori project — jangan ulangi kesalahan ini):"
        return header + "\n".join("- " + b.strip().replace("\n", " ") for b in relevant[-5:])

    def _load_project_styleguide(self, job: Job, task: Task) -> str:
        """Baca style-guide dara (bila ada) untuk task frontend.

        Mengatasi masalah "dev tidak membaca style-guide dara": tanpa ini
        output dev memakai palet/ikon sendiri sehingga hasil tak kohesif.
        """
        if self.workspace_base is None:
            return ""
        frontend_agents = ("dev", "dara", "qa")
        keywords = (
            "html", "css", "tailwind", "javascript", "landing", "frontend",
            "web", "desain", "ui", "halaman", "interface", "tampilan",
        )
        desc = f"{task.description} {task.input}".lower()
        if task.agent_name not in frontend_agents and not any(
            k in desc for k in keywords
        ):
            return ""
        base = self.workspace_base / self._slug_for(job)
        for candidate in (base / "design" / "style-guide.md", base / "style-guide.md"):
            if candidate.exists():
                try:
                    content = candidate.read_text(encoding="utf-8")[:4000]
                except OSError as exc:  # noqa: BLE001
                    logger.warning("Gagal membaca style-guide: %s", exc)
                    return ""
                return (
                    "STYLE GUIDE PROYEK (DIBUAT DARA — WAJIB DIIKUTI, "
                    "jangan ganti palet/tipografi/ikon):\n" + content
                )
        return ""

    def _run_task(self, job_id: str, task: Task, report: RunReport) -> None:
        self._emit(f"[{task.agent_name}] mulai: {task.description[:80]}", job_id)
        self.storage.update_task(task.id, status=TaskStatus.IN_PROGRESS.value)

        agent = self.registry.get(task.agent_name)
        if agent is None:
            self._fail_task(task, report, error=f"Agent '{task.agent_name}' tidak ada di registry.")
            return

        context = retrieve_context(
            self.storage, self.embedder, job_id, query=task.description
        )
        job = self.storage.get_job(job_id)
        if job is not None:
            lessons = self._load_learnings(job, task.agent_name)
            if lessons:
                context = f"{context}\n\n{lessons}" if context else lessons
            styleguide = self._load_project_styleguide(job, task)
            if styleguide:
                context = f"{context}\n\n{styleguide}" if context else styleguide
            snapshot = self._project_snapshot(job)
            if snapshot:
                context = f"{context}\n\n{snapshot}" if context else snapshot
            status = self._load_project_status(job)
            if status:
                context = f"{context}\n\n{status}" if context else status
        result = agent.execute(task, context=context)

        if not result.success:
            self._retry_or_fail(task, report, result, error=result.error or "eksekusi gagal")
            return

        # ------- review (opsional) -------
        if self.reviewer_enabled:
            self._emit(f"[{task.agent_name}] mengirim ke review", job_id)
            evidence = self._collect_evidence(job, task, result)
            verdict = self._review(task, result, evidence)
            if not verdict.approved:
                report.revisions += 1
                task.review_count = task.review_count + 1
                if task.review_count >= self.max_review_rounds:
                    self._emit(
                        f"[{task.agent_name}] review maksimal tercapai, terima apa adanya", job_id
                    )
                    self.storage.update_task(
                        task.id,
                        status=TaskStatus.DONE.value,
                        output=result.output,
                        review_count=task.review_count,
                        error=f"review terakhir: {verdict.feedback}",
                    )
                    report.tasks_done += 1
                    return
                self._emit(f"[{task.agent_name}] revisi diminta: {verdict.feedback[:80]}", job_id)
                job = self.storage.get_job(job_id)
                if job is not None:
                    self._append_lesson(job, task, verdict.feedback)
                self.storage.update_task(
                    task.id,
                    status=TaskStatus.PENDING.value,
                    input={**(task.input or {}), "revisi": verdict.feedback,
                           "_attempt": task.retry_count + 1},
                    review_count=task.review_count,
                )
                return

        self.storage.update_task(
            task.id,
            status=TaskStatus.DONE.value,
            output=result.output,
            error=None,
        )
        report.tasks_done += 1
        self._emit(f"[{task.agent_name}] selesai ✓", job_id)
        job = self.storage.get_job(job_id)
        if job is not None:
            self._update_project_status(job, task, result)

    def _review(self, task: Task, result: AgentResult, evidence: str = ""):
        reviewer = self.registry.get("vera")
        if reviewer is None or not hasattr(reviewer, "review"):
            from ailabs.models.agent_result import ReviewVerdict

            return ReviewVerdict(approved=True)
        return reviewer.review(task, result, evidence=evidence)

    def _retry_or_fail(self, task: Task, report: RunReport, result: AgentResult, error: str) -> None:
        task.retry_count += 1
        if task.retry_count > self.max_exec_retries:
            self._fail_task(task, report, error=error)
            return
        self._emit(f"[{task.agent_name}] retry {task.retry_count}/{self.max_exec_retries}: {error[:80]}", task.job_id)
        self.storage.update_task(
            task.id,
            status=TaskStatus.READY.value,
            retry_count=task.retry_count,
            error=error,
        )

    def _fail_task(self, task: Task, report: RunReport, error: str) -> None:
        self.storage.update_task(
            task.id, status=TaskStatus.FAILED.value, error=error
        )
        report.tasks_failed += 1
        self._emit(f"[{task.agent_name}] GAGAL: {error}", task.job_id)

    def _fail_stuck(self, job_id: str, report: RunReport) -> None:
        pending = self.storage.get_tasks(job_id)
        blocked = [t.id for t in pending if t.status in ("pending", "ready", "in_progress")]
        msg = f"Tidak ada task yang siap dieksekusi (blocked/cycle): {blocked}"
        self.storage.update_job(job_id, status="failed", final_report=msg)
        self._emit("JOB GAGAL: " + msg, job_id)

    def _synthesize(self, job: Job, report: RunReport) -> None:
        self._emit("[mark] menyusun laporan akhir", job.id)
        ceo = self.registry.get("mark")
        if ceo is not None and hasattr(ceo, "synthesize"):
            tasks = self.storage.get_tasks(job.id)
            summary = "\n\n".join(
                f"- {t.agent_name} / {t.status}: {t.description}\n  {(t.output or {}).get('text', '')[:300]}"
                for t in tasks
            )
            try:
                report_text = ceo.synthesize(job.user_prompt, summary)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sintesis gagal, pakai ringkasan lokal: %s", exc)
                report_text = self._local_summary(job)
        else:
            report_text = self._local_summary(job)

        self.storage.create_document(self._report_doc(job, report_text))
        self.storage.update_job(
            job.id, status="done", final_report=report_text
        )
        report.job = self.storage.get_job(job.id)
        self._emit("[mark] job SELESAI ✓", job.id)

    @staticmethod
    def _local_summary(job: Job) -> str:
        return (
            f"# Laporan {job.user_prompt[:60]}\n\n"
            f"Job {job.id} selesai. Lihat detail per-task di `ailabs status {job.id}`."
        )

    @staticmethod
    def _report_doc(job: Job, text: str):
        from ailabs.models.document import DocType, Document

        return Document(
            id="", job_id=job.id, title="Laporan Akhir", content=text,
            doc_type=DocType.REPORT.value, agent="mark",
        )

    def _emit(self, msg: str, job_id: str) -> None:
        logger.info("[%s] %s", job_id[:8], msg)
        self.on_event(msg, job_id)
