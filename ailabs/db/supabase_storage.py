"""Storage via Supabase (Postgres + pgvector).

Perlu SUPABASE_URL + SUPABASE_ANON_KEY di .env. Jalankan schema di
`db/schema.sql` lewat Supabase SQL editor dulu.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ailabs.config.settings import Settings
from ailabs.db.base import Storage, _now
from ailabs.models.document import Document
from ailabs.models.job import Job
from ailabs.models.task import Task, TaskSpec

logger = logging.getLogger(__name__)

# Kolom yang boleh di-update (mencegah injeksi field aneh ke postgrest).
_JOB_FIELDS = {"status", "final_report", "created_by", "project"}
_TASK_FIELDS = {
    "status",
    "output",
    "error",
    "retry_count",
    "review_count",
    "input",
    "depends_on",
}


def _pick(row: dict, fields: set[str]) -> dict:
    return {k: v for k, v in row.items() if k in fields and v is not None}


class SupabaseStorage(Storage):
    def __init__(
        self,
        url: str,
        key: str,
        schema: str = "ailabs",
    ):
        if not url or not key:
            raise ValueError("SUPABASE_URL / key belum diset di .env")
        try:
            from supabase import ClientOptions, create_client
        except ImportError as exc:
            raise ImportError(
                "Paket 'supabase' belum terinstall. Jalankan: pip install -r requirements.txt"
            ) from exc
        self._client = create_client(url, key, options=ClientOptions(schema=schema))

    def _execute(self, builder, retries: int = 3):
        """Eksekusi query dengan retry pada error koneksi (HTTP/2 'Server disconnected').

        postgrest mengaktifkan http2=True; koneksi idle yang ditutup server bisa
        memunculkan RemoteProtocolError/ConnectError saat burst request. Retry
        ringan menutup kesalahan tersebut tanpa mengubah pemanggilan lain.
        """
        import time

        try:
            import httpx
        except ImportError:  # pragma: no cover
            httpx = None
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                return builder.execute()
            except Exception as exc:  # noqa: BLE001
                if httpx is None or not isinstance(
                    exc, (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TransportError)
                ):
                    raise
                last_exc = exc
                logger.warning(
                    "Supabase transport error (percobaan %s/%s): %s",
                    attempt + 1,
                    retries,
                    exc,
                )
                time.sleep(0.35 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    # ---------- jobs ----------
    def create_job(
        self,
        user_prompt: str,
        created_by: str | None = None,
        project: str | None = None,
    ) -> Job:
        row = self._execute(
            self._client.table("jobs").insert(
                {
                    "user_prompt": user_prompt,
                    "status": "pending",
                    "created_by": created_by,
                    "project": project,
                }
            )
        ).data[0]
        return Job(**row)

    def get_job(self, job_id: str) -> Job | None:
        rows = self._execute(
            self._client.table("jobs").select("*").eq("id", job_id)
        ).data
        return Job(**rows[0]) if rows else None

    def update_job(self, job_id: str, **fields) -> Job | None:
        payload = _pick(fields, _JOB_FIELDS)
        if not payload:
            return self.get_job(job_id)
        payload["updated_at"] = _now()
        rows = self._execute(
            self._client.table("jobs").update(payload).eq("id", job_id)
        ).data
        return Job(**rows[0]) if rows else None

    def list_jobs(self, limit: int = 20) -> list[Job]:
        rows = self._execute(
            self._client.table("jobs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        ).data
        return [Job(**r) for r in rows]

    # ---------- tasks ----------
    def create_tasks(
        self, job_id: str, specs: list[TaskSpec], ids: list[str] | None = None
    ) -> list[Task]:
        if not specs:
            return []
        payloads = []
        for i, spec in enumerate(specs):
            row = {
                "job_id": job_id,
                "description": spec.description,
                "agent_name": spec.agent_name,
                "status": "pending",
                "depends_on": spec.depends_on,
                "input": spec.input or {},
            }
            if ids:
                row["id"] = ids[i]
            payloads.append(row)
        rows = self._execute(self._client.table("tasks").insert(payloads)).data
        return [Task(**r) for r in rows]

    def get_tasks(self, job_id: str) -> list[Task]:
        rows = self._execute(
            self._client.table("tasks")
            .select("*")
            .eq("job_id", job_id)
            .order("created_at")
        ).data
        return [Task(**r) for r in rows]

    def get_task(self, task_id: str) -> Task | None:
        rows = self._execute(
            self._client.table("tasks").select("*").eq("id", task_id)
        ).data
        return Task(**rows[0]) if rows else None

    def update_task(self, task_id: str, **fields) -> Task | None:
        payload = _pick(fields, _TASK_FIELDS)
        if not payload:
            return self.get_task(task_id)
        payload["updated_at"] = _now()
        rows = self._execute(
            self._client.table("tasks").update(payload).eq("id", task_id)
        ).data
        return Task(**rows[0]) if rows else None

    # ---------- documents ----------
    def create_document(self, document: Document) -> Document:
        payload = document.model_dump()
        if not payload.get("id"):
            payload.pop("id", None)          # biarkan DB generate uuid
        if payload.get("created_at") is None:
            payload.pop("created_at", None)  # biarkan DB default now()
        row = self._execute(self._client.table("documents").insert(payload)).data[0]
        return Document(**row)

    def list_documents(self, job_id: str) -> list[Document]:
        rows = self._execute(
            self._client.table("documents").select("*").eq("job_id", job_id)
        ).data
        return [Document(**r) for r in rows]

    def get_all_documents(self) -> list[Document]:
        rows = self._execute(self._client.table("documents").select("*")).data
        return [Document(**r) for r in rows]

    # ---------- operasional dashboard / maintenance ----------
    def get_all_tasks(self) -> list[Task]:
        rows = self._execute(self._client.table("tasks").select("*")).data
        return [Task(**r) for r in rows]

    def count_jobs(self) -> int:
        res = self._execute(
            self._client.table("jobs").select("id", count="exact", head=True)
        )
        return res.count or 0

    def count_tasks(self) -> int:
        res = self._execute(
            self._client.table("tasks").select("id", count="exact", head=True)
        )
        return res.count or 0

    def count_documents(self) -> int:
        res = self._execute(
            self._client.table("documents").select("id", count="exact", head=True)
        )
        return res.count or 0

    def failed_task_count(self) -> int:
        res = self._execute(
            self._client.table("tasks")
            .select("id", count="exact", head=True)
            .eq("status", "failed")
        )
        return res.count or 0

    def list_failed_tasks(self, limit: int = 60) -> list[Task]:
        rows = self._execute(
            self._client.table("tasks")
            .select("id,job_id,description,agent_name,status,error,retry_count,updated_at")
            .eq("status", "failed")
            .order("updated_at", desc=True)
            .limit(limit)
        ).data
        return [Task(**r) for r in rows]

    def task_counts_by_job(self, job_ids: list[str]) -> dict[str, dict]:
        if not job_ids:
            return {}
        rows = self._execute(
            self._client.table("tasks")
            .select("job_id,status")
            .in_("job_id", job_ids)
        ).data
        out: dict[str, dict] = {}
        for r in rows:
            c = out.setdefault(r["job_id"], {"total": 0, "done": 0, "failed": 0})
            c["total"] += 1
            if r["status"] == "done":
                c["done"] += 1
            elif r["status"] == "failed":
                c["failed"] += 1
        return out

    def task_stats_by_agent(self) -> dict[str, dict]:
        rows = self._execute(
            self._client.table("tasks")
            .select("agent_name,status,review_count,created_at,updated_at")
        ).data
        out: dict[str, dict] = {}
        for r in rows:
            a = r.get("agent_name") or "?"
            row = out.setdefault(
                a,
                {"task_count": 0, "done": 0, "failed": 0, "reviews": 0,
                 "avg_seconds": None, "_sum": 0.0, "_n": 0},
            )
            row["task_count"] += 1
            st = r.get("status")
            if st == "done":
                row["done"] += 1
                if r.get("created_at") and r.get("updated_at"):
                    try:
                        c = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                        u = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                        row["_sum"] += (u - c).total_seconds()
                        row["_n"] += 1
                    except ValueError:
                        pass
            elif st == "failed":
                row["failed"] += 1
            row["reviews"] += r.get("review_count") or 0
        for row in out.values():
            row["avg_seconds"] = (row["_sum"] / row["_n"]) if row["_n"] else None
            row.pop("_sum", None)
            row.pop("_n", None)
        return out

    def batch_update_tasks(
        self, job_id: str, from_statuses: list[str], **fields
    ) -> int:
        payload = _pick(fields, _TASK_FIELDS)
        if not payload or not from_statuses:
            return 0
        payload["updated_at"] = _now()
        rows = self._execute(
            self._client.table("tasks")
            .update(payload)
            .eq("job_id", job_id)
            .in_("status", from_statuses)
        ).data
        return len(rows)

    def delete_failed_jobs(self) -> int:
        rows = self._execute(
            self._client.table("jobs").select("id").eq("status", "failed")
        ).data
        ids = [r["id"] for r in rows]
        if not ids:
            return 0
        self._execute(self._client.table("tasks").delete().in_("job_id", ids))
        self._execute(self._client.table("documents").delete().in_("job_id", ids))
        self._execute(self._client.table("jobs").delete().in_("id", ids))
        return len(ids)

    def delete_job(self, job_id: str) -> bool:
        if not self.get_job(job_id):
            return False
        self._execute(self._client.table("tasks").delete().eq("job_id", job_id))
        self._execute(self._client.table("documents").delete().eq("job_id", job_id))
        self._execute(self._client.table("jobs").delete().eq("id", job_id))
        return True

    def clear_all(self) -> None:
        self._execute(
            self._client.table("documents").delete().gte("created_at", "1970-01-01")
        )
        self._execute(self._client.table("tasks").delete().gte("created_at", "1970-01-01"))
        self._execute(self._client.table("jobs").delete().gte("created_at", "1970-01-01"))

    # ---------- migrasi ----------
    def migrate_from(self, source: Storage) -> dict:
        """Salin semua data dari storage lain (mis. JSON lokal) ke Supabase.

        Memakai id asal supaya relasi job/task/doc tetap utuh. Mengembalikan
        hitungan per tabel; melempar Exception kalau gagal.
        """
        counts = {"jobs": 0, "tasks": 0, "documents": 0}

        for job in source.list_jobs(limit=10000):
            self._execute(
                self._client.table("jobs").upsert(
                    {
                        "id": job.id,
                        "user_prompt": job.user_prompt,
                        "project": job.project,
                        "status": job.status,
                        "created_by": job.created_by,
                        "final_report": job.final_report,
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                    }
                )
            )
            counts["jobs"] += 1

        for task in source.get_all_tasks():
            self._execute(
                self._client.table("tasks").upsert(
                    {
                        "id": task.id,
                        "job_id": task.job_id,
                        "description": task.description,
                        "agent_name": task.agent_name,
                        "status": task.status,
                        "depends_on": task.depends_on,
                        "input": task.input or {},
                        "output": task.output,
                        "error": task.error,
                        "retry_count": task.retry_count,
                        "review_count": task.review_count,
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                    }
                )
            )
            counts["tasks"] += 1

        for job in source.list_jobs(limit=10000):
            for doc in source.list_documents(job.id):
                self._execute(
                    self._client.table("documents").upsert(
                        {
                            "id": doc.id,
                            "job_id": doc.job_id,
                            "task_id": doc.task_id,
                            "title": doc.title,
                            "content": doc.content,
                            "doc_type": doc.doc_type,
                            "agent": doc.agent,
                            "metadata": doc.metadata or {},
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        }
                    )
                )
                counts["documents"] += 1

        return counts


def build_storage(settings: Settings | None = None) -> Storage:
    """Supabase kalau dikonfigurasi; kalau tidak, JSON file lokal (data persisten).

    Key yang dipakai: SECRET (bypass RLS) > PUBLISHABLE (RLS aktif) > ANON (legacy).
    Semua tabel ditaruh di schema tersendiri (`ailabs`) supaya tidak bercampur
    dengan tabel user di `public`.
    """
    settings = settings or Settings()
    key = (
        settings.supabase_secret_key
        or settings.supabase_publishable_key
        or settings.supabase_anon_key
    )
    if settings.supabase_url and key:
        return SupabaseStorage(
            settings.supabase_url, key, schema=settings.supabase_schema
        )
    from pathlib import Path

    from ailabs.config.settings import PROJECT_ROOT
    from ailabs.db.base import JsonFileStorage

    path = Path(PROJECT_ROOT) / "data" / "ailabs.json"
    logger.warning(
        "Supabase belum dikonfigurasi (SUPABASE_URL + salah satu key) — memakai "
        "JSON file lokal (%s). Isi .env untuk memakai Supabase schema '%s'.",
        path,
        settings.supabase_schema,
    )
    return JsonFileStorage(path)
