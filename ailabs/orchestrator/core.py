"""AILabsOrchestrator — entrypoint utama.

submit  -> simpan job (pending)
plan    -> Mark buat TaskGraph + simpan tasks + dokumen plan
run     -> execution loop (workers -> review -> sintesis)
ask     -> submit + plan + run (satu perintah)
"""

from __future__ import annotations

import logging
from pathlib import Path

from ailabs.agents.registry import AgentRegistry
from ailabs.config.settings import PROJECT_ROOT, Settings
from ailabs.db.base import Storage
from ailabs.db.supabase_storage import build_storage
from ailabs.llm.factory import build_llm
from ailabs.memory.vector_store import build_embedder
from ailabs.orchestrator.executor import Executor, RunReport
from ailabs.orchestrator.planner import Planner

logger = logging.getLogger(__name__)


class AILabsOrchestrator:
    def __init__(
        self,
        storage: Storage | None = None,
        settings: Settings | None = None,
        on_event=None,
    ):
        self.settings = settings or Settings()
        self.storage = storage or build_storage(self.settings)
        self.llm = build_llm(self.settings)
        self.embedder = build_embedder(self.settings)

        from ailabs.skills.registry import SkillRegistry

        workspace_root = (
            Path(self.settings.local_workspace_path)
            if self.settings.local_workspace_path
            else Path(PROJECT_ROOT) / "workspace"
        )
        self.workspace_path = workspace_root
        self._skill_log: list[dict] = []
        self.skills = SkillRegistry(
            context={
                "obsidian_vault_path": self.settings.obsidian_vault_path,
                "workspace_path": str(workspace_root),
            }
        )
        self.skills.inject_context(
            storage=self.storage,
            embedder=self.embedder,
            llm=self.llm,
            skills=self.skills,
            agentic_max_iterations=self.settings.agentic_max_iterations,
            _skill_log=self._skill_log,
            enable_opencode=self.settings.enable_opencode,
        )

        self.registry = AgentRegistry(
            llm=self.llm, skills=self.skills, settings=self.settings
        )
        self.planner = Planner(self.llm, self.registry, self.storage)
        self.executor = Executor(
            self.storage,
            self.registry,
            reviewer_enabled=self.settings.reviewer_enabled,
            max_exec_retries=self.settings.max_exec_retries,
            max_review_rounds=self.settings.max_review_rounds,
            embedder=self.embedder,
            skills=self.skills,
            workspace_base=self.workspace_path,
            on_event=on_event,
        )

    # ---------- API publik ----------

    def submit(
        self,
        prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ):
        """Simpan job (status pending) lalu rencanakan oleh Mark."""
        from ailabs.utils import slugify

        project = slugify(project) if project else None
        job = self.storage.create_job(prompt, created_by=created_by, project=project)
        self.planner.plan(job)
        return self.storage.get_job(job.id)

    def run(self, job_id: str) -> RunReport:
        return self.executor.execute_job(job_id)

    def ask(
        self,
        prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ) -> RunReport:
        """submit + plan + run sekaligus."""
        job = self.submit(prompt, created_by=created_by, project=project)
        return self.run(job.id)

    def status(self, job_id: str):
        return self.storage.get_job(job_id)

    def tasks(self, job_id: str):
        return self.storage.get_tasks(job_id)

    def reports(self, job_id: str):
        return self.storage.list_documents(job_id)

    def all_documents(self):
        return self.storage.get_all_documents()

    def roster(self) -> str:
        return self.registry.roster()

    def skill_log(self):
        return list(self._skill_log)

    # ---------- operasional dashboard / maintenance ----------

    def all_jobs(self, limit: int = 50):
        return self.storage.list_jobs(limit=limit)

    def all_tasks(self):
        return self.storage.get_all_tasks()

    def counts(self) -> dict:
        """Hitungan ringan (COUNT) tanpa menarik isi tabel."""
        return {
            "jobs": self.storage.count_jobs(),
            "tasks": self.storage.count_tasks(),
            "documents": self.storage.count_documents(),
        }

    def failed_tasks(self, limit: int = 60):
        return self.storage.list_failed_tasks(limit=limit)

    def failed_task_count(self) -> int:
        return self.storage.failed_task_count()

    def task_counts_by_job(self, job_ids: list[str]) -> dict[str, dict]:
        return self.storage.task_counts_by_job(job_ids)

    def task_stats(self) -> dict[str, dict]:
        return self.storage.task_stats_by_agent()

    def delete_job(self, job_id: str) -> bool:
        return self.storage.delete_job(job_id)

    def delete_failed_jobs(self) -> int:
        return self.storage.delete_failed_jobs()

    def clear_all(self) -> None:
        self.storage.clear_all()

    # ---------- aksi dari dashboard ----------

    def retry_task(self, task_id: str):
        """Reset task failed -> ready supaya dieksekusi ulang."""
        task = self.storage.get_task(task_id)
        if task is None:
            return None
        if task.status != "failed":
            return task
        return self.storage.update_task(
            task_id, status="ready", error=None
        )

    def cancel_job(self, job_id: str):
        """Hentikan job: task yang belum selesai ditandai failed (1 query batch)."""
        job = self.storage.get_job(job_id)
        if job is None or job.is_finished:
            return job
        self.storage.batch_update_tasks(
            job_id,
            from_statuses=["pending", "ready", "in_progress"],
            status="failed",
            error="dibatalkan oleh user",
        )
        return self.storage.update_job(
            job_id, status="failed", final_report="Job dibatalkan oleh user."
        )
