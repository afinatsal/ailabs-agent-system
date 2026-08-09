"""Abstraksi storage + implementasi in-memory (untuk dev/test).

Tujuan: orchestrator tidak tahu menahu apakah data disimpan di Supabase,
Postgres, atau RAM. Ganti penyimpanan = ganti satu class.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from ailabs.models.document import Document
from ailabs.models.job import Job
from ailabs.models.task import Task, TaskSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class Storage(ABC):
    """Kontrak minimal yang dibutuhkan orchestrator."""

    # ---------- jobs ----------
    @abstractmethod
    def create_job(
        self,
        user_prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ) -> Job: ...

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def update_job(self, job_id: str, **fields) -> Job | None: ...

    @abstractmethod
    def list_jobs(self, limit: int = 20) -> list[Job]: ...

    # ---------- tasks ----------
    @abstractmethod
    def create_tasks(
        self,
        job_id: str,
        specs: list[TaskSpec],
        ids: list[str] | None = None,
    ) -> list[Task]: ...

    @abstractmethod
    def get_tasks(self, job_id: str) -> list[Task]: ...

    @abstractmethod
    def get_task(self, task_id: str) -> Task | None: ...

    @abstractmethod
    def update_task(self, task_id: str, **fields) -> Task | None: ...

    # ---------- documents ----------
    @abstractmethod
    def create_document(self, document: Document) -> Document: ...

    @abstractmethod
    def list_documents(self, job_id: str) -> list[Document]: ...

    @abstractmethod
    def get_all_documents(self) -> list[Document]: ...

    # ---------- operasional dashboard / maintenance ----------
    @abstractmethod
    def get_all_tasks(self) -> list[Task]: ...

    @abstractmethod
    def delete_job(self, job_id: str) -> bool: ...

    @abstractmethod
    def clear_all(self) -> None: ...

    # ---------- agregasi ringan untuk dashboard (tanpa kolom besar) ----------
    @abstractmethod
    def count_jobs(self) -> int: ...

    @abstractmethod
    def count_tasks(self) -> int: ...

    @abstractmethod
    def count_documents(self) -> int: ...

    @abstractmethod
    def failed_task_count(self) -> int: ...

    @abstractmethod
    def list_failed_tasks(self, limit: int = 60) -> list[Task]: ...

    @abstractmethod
    def task_counts_by_job(self, job_ids: list[str]) -> dict[str, dict]: ...

    @abstractmethod
    def task_stats_by_agent(self) -> dict[str, dict]: ...

    @abstractmethod
    def batch_update_tasks(
        self, job_id: str, from_statuses: list[str], **fields
    ) -> int: ...

    @abstractmethod
    def delete_failed_jobs(self) -> int: ...

    # ---------- helpers ----------
    def get_ready_tasks(self, job_id: str) -> list[Task]:
        """Task yang dependency-nya sudah selesai & belum dikerjakan."""
        tasks = self.get_tasks(job_id)
        done_ids = {t.id for t in tasks if t.status == "done"}
        ready = []
        for t in tasks:
            if t.status in ("ready", "pending", "failed"):
                if all(dep in done_ids for dep in t.depends_on):
                    ready.append(t)
        return ready

    def has_remaining(self, job_id: str) -> bool:
        tasks = self.get_tasks(job_id)
        return any(t.status not in ("done", "failed") for t in tasks)


class InMemoryStorage(Storage):
    """Simpan semua di dict Python. Data hilang saat proses berhenti."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._tasks: dict[str, dict] = {}
        self._docs: dict[str, dict] = {}

    # ---------- jobs ----------
    def create_job(
        self,
        user_prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ) -> Job:
        now = _now()
        data = {
            "id": _uid(),
            "user_prompt": user_prompt,
            "project": project,
            "status": "pending",
            "created_by": created_by,
            "final_report": None,
            "created_at": now,
            "updated_at": now,
        }
        self._jobs[data["id"]] = data
        return Job(**data)

    def get_job(self, job_id: str) -> Job | None:
        data = self._jobs.get(job_id)
        return Job(**data) if data else None

    def update_job(self, job_id: str, **fields) -> Job | None:
        data = self._jobs.get(job_id)
        if not data:
            return None
        data.update(fields)
        data["updated_at"] = _now()
        return Job(**data)

    def list_jobs(self, limit: int = 20) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return [Job(**j) for j in jobs[:limit]]

    # ---------- tasks ----------
    def create_tasks(
        self, job_id: str, specs: list[TaskSpec], ids: list[str] | None = None
    ) -> list[Task]:
        created: list[Task] = []
        for i, spec in enumerate(specs):
            now = _now()
            data = {
                **spec.model_dump(),
                "id": ids[i] if ids else _uid(),
                "job_id": job_id,
                "status": "pending",
                "output": None,
                "error": None,
                "retry_count": 0,
                "review_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            self._tasks[data["id"]] = data
            created.append(Task(**data))
        return created

    def get_tasks(self, job_id: str) -> list[Task]:
        return [Task(**t) for t in self._tasks.values() if t["job_id"] == job_id]

    def get_task(self, task_id: str) -> Task | None:
        data = self._tasks.get(task_id)
        return Task(**data) if data else None

    def update_task(self, task_id: str, **fields) -> Task | None:
        data = self._tasks.get(task_id)
        if not data:
            return None
        data.update(fields)
        data["updated_at"] = _now()
        return Task(**data)

    # ---------- documents ----------
    def create_document(self, document: Document) -> Document:
        data = document.model_dump()
        if not data.get("id"):
            data["id"] = _uid()
        self._docs[data["id"]] = data
        return Document(**data)

    def list_documents(self, job_id: str) -> list[Document]:
        return [Document(**d) for d in self._docs.values() if d["job_id"] == job_id]

    def get_all_documents(self) -> list[Document]:
        return [Document(**d) for d in self._docs.values()]

    # ---------- operasional dashboard / maintenance ----------
    def get_all_tasks(self) -> list[Task]:
        return [Task(**t) for t in self._tasks.values()]

    def count_jobs(self) -> int:
        return len(self._jobs)

    def count_tasks(self) -> int:
        return len(self._tasks)

    def count_documents(self) -> int:
        return len(self._docs)

    def failed_task_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t["status"] == "failed")

    def list_failed_tasks(self, limit: int = 60) -> list[Task]:
        rows = sorted(
            (t for t in self._tasks.values() if t["status"] == "failed"),
            key=lambda t: str(t.get("updated_at") or ""),
            reverse=True,
        )
        return [Task(**t) for t in rows[:limit]]

    def task_counts_by_job(self, job_ids: list[str]) -> dict[str, dict]:
        ids = set(job_ids)
        out: dict[str, dict] = {}
        for t in self._tasks.values():
            if t["job_id"] not in ids:
                continue
            c = out.setdefault(t["job_id"], {"total": 0, "done": 0, "failed": 0})
            c["total"] += 1
            if t["status"] == "done":
                c["done"] += 1
            elif t["status"] == "failed":
                c["failed"] += 1
        return out

    def task_stats_by_agent(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for t in self._tasks.values():
            a = t["agent_name"]
            row = out.setdefault(
                a,
                {"task_count": 0, "done": 0, "failed": 0, "reviews": 0, "avg_seconds": None,
                 "_sum": 0.0, "_n": 0},
            )
            row["task_count"] += 1
            if t["status"] == "done":
                row["done"] += 1
                if t.get("created_at") and t.get("updated_at"):
                    try:
                        c = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
                        u = datetime.fromisoformat(t["updated_at"].replace("Z", "+00:00"))
                        row["_sum"] += (u - c).total_seconds()
                        row["_n"] += 1
                    except ValueError:
                        pass
            elif t["status"] == "failed":
                row["failed"] += 1
            row["reviews"] += t.get("review_count") or 0
        for row in out.values():
            row["avg_seconds"] = (row["_sum"] / row["_n"]) if row["_n"] else None
            row.pop("_sum", None)
            row.pop("_n", None)
        return out

    def batch_update_tasks(
        self, job_id: str, from_statuses: list[str], **fields
    ) -> int:
        n = 0
        statuses = set(from_statuses)
        for tid, t in self._tasks.items():
            if t["job_id"] == job_id and t["status"] in statuses:
                self._tasks[tid].update(fields)
                self._tasks[tid]["updated_at"] = _now()
                n += 1
        return n

    def delete_failed_jobs(self) -> int:
        ids = [j["id"] for j in self._jobs.values() if j["status"] == "failed"]
        for jid in ids:
            self.delete_job(jid)
        return len(ids)

    def delete_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        for tid in [t["id"] for t in self._tasks.values() if t["job_id"] == job_id]:
            self._tasks.pop(tid, None)
        for did in [d["id"] for d in self._docs.values() if d["job_id"] == job_id]:
            self._docs.pop(did, None)
        self._jobs.pop(job_id, None)
        return True

    def clear_all(self) -> None:
        self._jobs.clear()
        self._tasks.clear()
        self._docs.clear()


class JsonFileStorage(InMemoryStorage):
    """Persist in-memory ke file JSON — pengganti Supabase untuk dev lokal.

    Supaya alur `submit` lalu `run`/`status` antar-proses CLI tetap berfungsi
    tanpa mengkonfigurasi Supabase.
    """

    def __init__(self, path: str | Path):
        super().__init__()
        self._path = Path(path)
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._jobs = data.get("jobs", {})
            self._tasks = data.get("tasks", {})
            self._docs = data.get("docs", {})

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"jobs": self._jobs, "tasks": self._tasks, "docs": self._docs},
                indent=2,
            ),
            encoding="utf-8",
        )

    # ---------- mutasi -> simpan ----------
    def create_job(
        self,
        user_prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ) -> Job:
        job = super().create_job(user_prompt, created_by=created_by, project=project)
        self._save()
        return job

    def update_job(self, job_id: str, **fields) -> Job | None:
        job = super().update_job(job_id, **fields)
        self._save()
        return job

    def create_tasks(
        self, job_id: str, specs: list[TaskSpec], ids: list[str] | None = None
    ) -> list[Task]:
        tasks = super().create_tasks(job_id, specs, ids=ids)
        self._save()
        return tasks

    def update_task(self, task_id: str, **fields) -> Task | None:
        task = super().update_task(task_id, **fields)
        self._save()
        return task

    def batch_update_tasks(
        self, job_id: str, from_statuses: list[str], **fields
    ) -> int:
        n = super().batch_update_tasks(job_id, from_statuses, **fields)
        self._save()
        return n

    def delete_failed_jobs(self) -> int:
        n = super().delete_failed_jobs()
        self._save()
        return n

    def create_document(self, document: Document) -> Document:
        doc = super().create_document(document)
        self._save()
        return doc

    def delete_job(self, job_id: str) -> bool:
        ok = super().delete_job(job_id)
        self._save()
        return ok

    def clear_all(self) -> None:
        super().clear_all()
        self._save()
