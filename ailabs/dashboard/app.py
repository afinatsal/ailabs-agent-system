"""AI Labs Dashboard — web UI (FastAPI + Jinja2 + vanilla JS).

Jalankan: `ailabs serve` (atau `uvicorn ailabs.dashboard:app`).
Satu process = satu orchestrator; data & event log dibagi antar request.
Job yang dijalankan dari dashboard dieksekusi di thread background agar
halaman tetap responsif dan bisa polling status live.
"""

from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ailabs.config.settings import Settings
from ailabs.db.base import Storage
from ailabs.db.supabase_storage import SupabaseStorage
from ailabs.memory.vector_store import SentenceTransformerEmbedder
from ailabs.orchestrator import AILabsOrchestrator

BASE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE / "templates"))
TEMPLATES.env.filters["md"] = lambda t: __import__(
    "ailabs.dashboard.markdown", fromlist=["render_md"]
).render_md(t)

from ailabs.dashboard.markdown import render_md  # noqa: E402

_STATUS_LABELS = {
    "pending": "Pending",
    "planning": "Planning",
    "running": "Running",
    "done": "Done",
    "failed": "Failed",
}

_MAX_EVENTS_PER_JOB = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _job_dict(job) -> dict:
    if job is None:
        return {}
    return {
        "id": job.id,
        "user_prompt": job.user_prompt,
        "project": job.project,
        "status": job.status,
        "status_label": _STATUS_LABELS.get(job.status, job.status),
        "created_by": job.created_by,
        "final_report": job.final_report,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "is_finished": job.is_finished,
    }


def _task_dict(task) -> dict:
    return {
        "id": task.id,
        "job_id": task.job_id,
        "description": task.description,
        "agent_name": task.agent_name,
        "status": task.status,
        "depends_on": list(task.depends_on),
        "input": task.input or {},
        "output": task.output or {},
        "error": task.error,
        "retry_count": task.retry_count,
        "review_count": task.review_count,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _job_light_dict(job) -> dict:
    """Tanpa final_report — untuk polling & daftar."""
    return {
        "id": job.id,
        "project": job.project,
        "status": job.status,
        "status_label": _STATUS_LABELS.get(job.status, job.status),
        "is_finished": job.is_finished,
    }


def _task_light_dict(task) -> dict:
    """Tanpa input/output (besar) — untuk polling."""
    return {
        "id": task.id,
        "job_id": task.job_id,
        "description": task.description,
        "agent_name": task.agent_name,
        "status": task.status,
        "depends_on": list(task.depends_on),
        "retry_count": task.retry_count,
        "created_at": _iso(task.created_at),
    }


def _doc_dict(doc) -> dict:
    return {
        "id": doc.id,
        "job_id": doc.job_id,
        "task_id": doc.task_id,
        "title": doc.title,
        "content": doc.content,
        "doc_type": doc.doc_type,
        "agent": doc.agent,
        "metadata": doc.metadata or {},
        "created_at": _iso(doc.created_at),
    }


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    """Factory: memungkinkan test menyuntik storage/settings tanpa .env asli."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        orch = _build_runtime(settings, storage, on_event=_on_event)
        app.state.orch = orch
        app.state.job_events: dict[str, list[dict]] = {}
        app.state.events_lock = threading.Lock()
        app.state.running_jobs: set[str] = set()
        app.state.running_lock = threading.Lock()
        yield

    app = FastAPI(title="AI Labs Dashboard", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    # ------------------------------------------------------------------ helpers

    def _on_event(msg: str, job_id: str) -> None:
        if not hasattr(app.state, "job_events"):
            return
        with app.state.events_lock:
            buf = app.state.job_events.setdefault(job_id, [])
            buf.append({"time": _now(), "msg": msg})
            if len(buf) > _MAX_EVENTS_PER_JOB:
                del buf[: len(buf) - _MAX_EVENTS_PER_JOB]

    def _mark_running(job_id: str, running: bool) -> None:
        with app.state.running_lock:
            if running:
                app.state.running_jobs.add(job_id)
            else:
                app.state.running_jobs.discard(job_id)

    def _is_running(job_id: str) -> bool:
        with app.state.running_lock:
            return job_id in app.state.running_jobs

    def _start_run(job_id: str) -> bool:
        """Mulai eksekusi job di thread background kalau belum running."""
        if _is_running(job_id):
            return False
        _mark_running(job_id, True)
        _on_event("Menjalankan job via dashboard", job_id)

        def worker():
            try:
                app.state.orch.run(job_id)
            except Exception as exc:  # noqa: BLE001
                _on_event(f"Run error: {exc}", job_id)
            finally:
                _mark_running(job_id, False)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _require_orch(request: Request) -> AILabsOrchestrator:
        return request.app.state.orch

    def _render(request: Request, template: str, **ctx) -> HTMLResponse:
        orch = _require_orch(request)
        ctx.setdefault("status_labels", _STATUS_LABELS)
        ctx.setdefault("provider", orch.settings.llm_provider)
        ctx.setdefault("storage_backend", _storage_backend(orch))
        ctx.setdefault("nav", template.split(".")[0])
        return TEMPLATES.TemplateResponse(request, template, ctx)

    def _safe_workspace_root(orch: AILabsOrchestrator) -> Path:
        return Path(orch.workspace_path)

    # ------------------------------------------------------------------ pages

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        orch = _require_orch(request)
        jobs = orch.all_jobs(limit=50)
        counts_by_job = orch.task_counts_by_job([j.id for j in jobs])

        today = datetime.now(timezone.utc).date()
        jobs_today = sum(1 for j in jobs if j.created_at and j.created_at.date() == today)
        jobs_week = sum(
            1
            for j in jobs
            if j.created_at
            and 0 <= (today - j.created_at.date()).days <= 7
        )

        done_jobs = [j for j in jobs if j.status == "done" and j.created_at and j.updated_at]
        avg_seconds = (
            sum((j.updated_at - j.created_at).total_seconds() for j in done_jobs)
            / len(done_jobs)
            if done_jobs
            else 0
        )

        status_counts = {s: 0 for s in _STATUS_LABELS}
        for j in jobs:
            status_counts[j.status] = status_counts.get(j.status, 0) + 1

        # activity feed: gabungkan event terbaru lintas job
        activity: list[dict] = []
        with app.state.events_lock:
            for job_id, buf in app.state.job_events.items():
                for e in buf[-20:]:
                    activity.append({"job_id": job_id, "time": e["time"], "msg": e["msg"]})
        activity.sort(key=lambda x: x["time"], reverse=True)
        activity = activity[:40]

        jobs_rows = []
        for j in jobs:
            c = counts_by_job.get(j.id, {})
            jobs_rows.append(
                {
                    "job": _job_dict(j),
                    "tasks_done": c.get("done", 0),
                    "tasks_failed": c.get("failed", 0),
                    "tasks_total": c.get("total", 0),
                    "running": _is_running(j.id),
                }
            )

        return _render(
            request,
            "overview.html",
            stats={
                "total_jobs": len(jobs),
                "jobs_today": jobs_today,
                "jobs_week": jobs_week,
                "avg_seconds": avg_seconds,
                "failed_tasks": orch.failed_task_count(),
                "status_counts": status_counts,
            },
            jobs=jobs_rows,
            activity=activity,
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: str):
        orch = _require_orch(request)
        job = orch.status(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        tasks = orch.tasks(job_id)
        docs = orch.reports(job_id)
        plan = next((d for d in docs if d.doc_type == "plan"), None)
        report = next((d for d in docs if d.doc_type == "report"), None)
        task_dicts = [_task_dict(t) for t in tasks]
        job_json = json.dumps(
            {"job": _job_dict(job), "tasks": task_dicts, "running": _is_running(job_id)}
        ).replace("</", "<\\/")
        return _render(
            request,
            "job_detail.html",
            job=_job_dict(job),
            tasks=task_dicts,
            plan=_doc_dict(plan) if plan else None,
            report=_doc_dict(report) if report else None,
            running=_is_running(job_id),
            job_id=job_id,
            job_json=job_json,
        )

    @app.get("/agents", response_class=HTMLResponse)
    def agents_page(request: Request):
        return _render(request, "agents.html", agents=_agent_stats(_require_orch(request)))

    @app.get("/skills", response_class=HTMLResponse)
    def skills_page(request: Request):
        orch = _require_orch(request)
        return _render(request, "skills.html", skills=_skill_stats(orch))

    @app.get("/workspace", response_class=HTMLResponse)
    def workspace_page(request: Request):
        orch = _require_orch(request)
        return _render(
            request,
            "workspace.html",
            tree=_workspace_tree(orch, _safe_workspace_root(orch)),
            root=str(_safe_workspace_root(orch)),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        orch = _require_orch(request)
        return _render(request, "settings.html", ** _settings_view(orch))

    @app.get("/logs", response_class=HTMLResponse)
    def logs_page(request: Request, job: str = ""):
        orch = _require_orch(request)
        jobs = orch.all_jobs(limit=100)
        failed = orch.failed_tasks(limit=60)
        events = _event_log(orch, app.state, job or None)
        return _render(
            request,
            "logs.html",
            jobs=[{"id": j.id, "project": j.project} for j in jobs],
            selected=job,
            failed=[_task_dict(t) for t in failed],
            events=events,
        )

    @app.get("/system_prompt/{agent_name}", response_class=PlainTextResponse)
    def system_prompt(agent_name: str):
        orch = app.state.orch
        agent = orch.registry.get(agent_name)
        if agent is None:
            raise HTTPException(404, "Agent tidak ditemukan")
        return PlainTextResponse(agent.system_prompt() or "(kosong)")

    # ------------------------------------------------------------------ actions

    @app.post("/submit")
    async def submit(request: Request):
        form = await request.form()
        prompt = (form.get("prompt") or "").strip()
        if not prompt:
            return RedirectResponse("/?toast=Prompt kosong", status_code=303)
        orch = _require_orch(request)
        job = orch.submit(
            prompt,
            created_by=(form.get("created_by") or None),
            project=(form.get("project") or None),
        )
        _start_run(job.id)
        return RedirectResponse(f"/jobs/{job.id}?toast=Job dibuat & dieksekusi", status_code=303)

    @app.post("/jobs/{job_id}/run")
    def run_job(request: Request, job_id: str):
        _start_run(job_id)
        return RedirectResponse(f"/jobs/{job_id}?toast=Eksekusi dimulai", status_code=303)

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(request: Request, job_id: str):
        orch = _require_orch(request)
        orch.cancel_job(job_id)
        return RedirectResponse(f"/jobs/{job_id}?toast=Job dibatalkan", status_code=303)

    @app.post("/jobs/{job_id}/delete")
    def delete_job(request: Request, job_id: str):
        orch = _require_orch(request)
        orch.delete_job(job_id)
        with app.state.events_lock:
            app.state.job_events.pop(job_id, None)
        return RedirectResponse("/?toast=Job dihapus", status_code=303)

    @app.post("/tasks/{task_id}/retry")
    def retry_task(request: Request, task_id: str):
        orch = _require_orch(request)
        task = orch.retry_task(task_id)
        if task is None:
            raise HTTPException(404, "Task tidak ditemukan")
        return RedirectResponse(f"/jobs/{task.job_id}?toast=Task dijadwalkan ulang", status_code=303)

    # ------------------------------------------------------------------ JSON API

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str):
        orch = app.state.orch
        job = orch.status(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        return {
            "job": _job_dict(job),
            "tasks": [_task_dict(t) for t in orch.tasks(job_id)],
            "running": _is_running(job_id),
        }

    @app.get("/api/jobs/{job_id}/poll")
    def api_job_poll(job_id: str, since: int = 0):
        """Polling ringan: metadata task + event baru saja (tanpa input/output)."""
        orch = app.state.orch
        job = orch.status(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        buf = app.state.job_events.get(job_id, [])
        return {
            "job": _job_light_dict(job),
            "tasks": [_task_light_dict(t) for t in orch.tasks(job_id)],
            "running": _is_running(job_id),
            "events": {"total": len(buf), "events": buf[since:]},
        }

    @app.get("/api/tasks/{task_id}")
    def api_task(task_id: str):
        """Detail task lengkap (input/output) — dimuat on-demand saat expand."""
        orch = app.state.orch
        task = orch.storage.get_task(task_id)
        if task is None:
            raise HTTPException(404, "Task tidak ditemukan")
        return _task_dict(task)

    @app.get("/api/jobs/{job_id}/report")
    def api_report_html(job_id: str):
        orch = app.state.orch
        job = orch.status(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        docs = orch.reports(job_id)
        report = next((d for d in docs if d.doc_type == "report"), None)
        text = (report.content if report else job.final_report) or None
        return {"html": render_md(text) if text else None}

    @app.get("/api/jobs/{job_id}/report.md")
    def api_report_md(job_id: str):
        orch = app.state.orch
        job = orch.status(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        docs = orch.reports(job_id)
        report = next((d for d in docs if d.doc_type == "report"), None)
        text = (report.content if report else job.final_report) or "(belum ada laporan)"
        return Response(
            text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="job-{job_id[:8]}-report.md"'},
        )

    @app.get("/api/jobs/{job_id}/events")
    def api_events(job_id: str, since: int = 0):
        buf = app.state.job_events.get(job_id, [])
        new = buf[since:]
        return {"events": new, "running": _is_running(job_id), "total": len(buf)}

    @app.post("/api/jobs/{job_id}/run")
    def api_run(job_id: str):
        started = _start_run(job_id)
        return {"ok": True, "started": started}

    @app.post("/api/jobs/{job_id}/cancel")
    def api_cancel(job_id: str):
        orch = app.state.orch
        job = orch.cancel_job(job_id)
        if job is None:
            raise HTTPException(404, "Job tidak ditemukan")
        return {"ok": True, "status": job.status}

    @app.post("/api/tasks/{task_id}/retry")
    def api_retry(task_id: str):
        orch = app.state.orch
        task = orch.retry_task(task_id)
        if task is None:
            raise HTTPException(404, "Task tidak ditemukan")
        return {"ok": True, "status": task.status}

    @app.post("/api/submit")
    async def api_submit(request: Request):
        body = await request.json()
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(400, "Prompt kosong")
        orch = app.state.orch
        job = orch.submit(
            prompt,
            created_by=body.get("created_by") or None,
            project=body.get("project") or None,
        )
        _start_run(job.id)
        return {"ok": True, "job_id": job.id}

    @app.get("/api/agents")
    def api_agents():
        return {"agents": _agent_stats(app.state.orch)}

    @app.post("/api/agents/{name}/toggle")
    def api_agent_toggle(name: str):
        orch = app.state.orch
        if orch.registry.get(name) is None:
            raise HTTPException(404, "Agent tidak ditemukan")
        enabled = _toggle_agent_config(name)
        return {"ok": True, "enabled": enabled}

    @app.get("/api/skills")
    def api_skills():
        return {"skills": _skill_stats(app.state.orch)}

    @app.get("/api/workspace")
    def api_workspace():
        orch = app.state.orch
        return {"root": str(_safe_workspace_root(orch)), "tree": _workspace_tree(orch, _safe_workspace_root(orch))}

    @app.get("/api/workspace/file")
    def api_workspace_file(path: str = Query(...)):
        orch = app.state.orch
        root = _safe_workspace_root(orch).resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "File tidak ditemukan")
        return Response(target.read_bytes(), media_type=_guess_mime(target))

    @app.get("/api/workspace/download")
    def api_workspace_download(path: str = Query(...)):
        orch = app.state.orch
        root = _safe_workspace_root(orch).resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "File tidak ditemukan")
        headers = {"Content-Disposition": f'attachment; filename="{target.name}"'}
        return Response(target.read_bytes(), media_type="application/octet-stream", headers=headers)

    @app.get("/api/settings")
    def api_settings():
        return _settings_view(app.state.orch)

    @app.post("/api/settings/llm-test")
    def api_llm_test():
        orch = app.state.orch
        try:
            orch.llm.generate("ping", "Balas satu kata: OK")
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @app.post("/api/settings/migrate")
    def api_migrate():
        orch = app.state.orch
        if isinstance(orch.storage, SupabaseStorage):
            return {"ok": True, "message": "Sudah memakai Supabase.", "counts": None}
        settings = orch.settings
        if not (settings.supabase_url and (settings.supabase_publishable_key or settings.supabase_secret_key or settings.supabase_anon_key)):
            return {"ok": False, "error": "Supabase belum dikonfigurasi di .env."}
        try:
            target = SupabaseStorage(
                settings.supabase_url,
                settings.supabase_publishable_key or settings.supabase_secret_key or settings.supabase_anon_key,
                schema=settings.supabase_schema,
            )
            counts = target.migrate_from(orch.storage)
            return {"ok": True, "counts": counts}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @app.post("/api/settings/clear")
    def api_clear_all():
        app.state.orch.clear_all()
        with app.state.events_lock:
            app.state.job_events.clear()
        return {"ok": True}

    @app.post("/api/settings/clear-failed")
    def api_clear_failed():
        orch = app.state.orch
        removed = orch.delete_failed_jobs()
        if removed:
            with app.state.events_lock:
                for jid in list(app.state.job_events):
                    if orch.status(jid) is None:
                        app.state.job_events.pop(jid, None)
        return {"ok": True, "removed": removed}

    @app.get("/api/health")
    def api_health():
        return _health(app.state.orch)

    return app


def _storage_backend(orch: AILabsOrchestrator) -> dict:
    sup = isinstance(orch.storage, SupabaseStorage)
    local_path = None
    if not sup:
        local_path = str(getattr(orch.storage, "_path", "in-memory"))
    return {"is_supabase": sup, "local_path": local_path}


# =================================================================== runtime

def _build_runtime(
    settings: Settings | None, storage: Storage | None, on_event=None
):
    """Bangun orchestrator; fallback ke mock bila tak ada API key."""
    from ailabs.llm.base import LLMError

    try:
        orch = AILabsOrchestrator(storage=storage, settings=settings, on_event=on_event)
    except LLMError:
        settings = settings or Settings(llm_provider="mock")
        orch = AILabsOrchestrator(storage=storage, settings=settings, on_event=on_event)
    return orch


# =================================================================== queries

def _agent_stats(orch: AILabsOrchestrator) -> list[dict]:
    stats = orch.task_stats()
    agents = []
    for a in orch.registry.all():
        s = stats.get(a.name, {})
        agents.append(
            {
                "name": a.name,
                "role": a.role,
                "description": a.description,
                "model": a.model or orch.settings.default_model,
                "enabled": True,
                "task_count": s.get("task_count", 0),
                "done": s.get("done", 0),
                "failed": s.get("failed", 0),
                "avg_seconds": s.get("avg_seconds"),
                "reviews": s.get("reviews", 0),
            }
        )
    for row in agents:
        row["success_rate"] = (
            row["done"] / row["task_count"] * 100 if row["task_count"] else None
        )
    agents.sort(key=lambda x: x["name"])
    return agents


def _skill_stats(orch: AILabsOrchestrator) -> list[dict]:
    skills = []
    prompts: dict[str, str] = {
        a.name: a.system_prompt().lower() for a in orch.registry.all()
    }
    for s in orch.skills.all():
        users = [name for name, p in prompts.items() if s.name in p]
        log = [e for e in orch.skill_log() if e.get("skill") == s.name][-8:]
        skills.append(
            {
                "name": s.name,
                "description": s.description,
                "needs_llm": s.needs_llm,
                "tags": s.tags,
                "users": users,
                "log": log,
            }
        )
    skills.sort(key=lambda x: x["name"])
    return skills


def _workspace_tree(orch: AILabsOrchestrator, root: Path) -> list[dict]:
    """Pohon file; folder project dipetakan ke job via slug project."""
    jobs_by_slug: dict[str, str] = {}
    for j in orch.all_jobs(limit=500):
        if j.project:
            jobs_by_slug.setdefault(j.project, j.id)

    def walk(path: Path) -> list[dict]:
        nodes = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return nodes
        for p in entries:
            if p.name.startswith(".") or p.name == ".DS_Store":
                continue
            if p.is_dir():
                nodes.append(
                    {
                        "name": p.name,
                        "type": "dir",
                        "path": str(p.relative_to(root)),
                        "children": walk(p),
                        "job_id": jobs_by_slug.get(p.name),
                    }
                )
            else:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                nodes.append(
                    {
                        "name": p.name,
                        "type": "file",
                        "path": str(p.relative_to(root)),
                        "size": size,
                        "job_id": jobs_by_slug.get(p.parent.name),
                    }
                )
        return nodes

    if not root.exists():
        return []
    return walk(root)


def _settings_view(orch: AILabsOrchestrator) -> dict:
    s = orch.settings
    sup_configured = bool(
        s.supabase_url
        and (s.supabase_publishable_key or s.supabase_secret_key or s.supabase_anon_key)
    )
    storage_backend = _storage_backend(orch)
    counts = orch.counts()
    return {
        "settings": {
            "provider": s.llm_provider,
            "default_model": s.default_model,
            "deepseek_model": s.deepseek_model,
            "gemini_key_set": bool(s.gemini_api_key),
            "deepseek_key_set": bool(s.deepseek_api_key),
            "supabase_configured": sup_configured,
            "supabase_url": s.supabase_url or "-",
            "schema": s.supabase_schema,
            "embedding_active": isinstance(orch.embedder, SentenceTransformerEmbedder),
            "embed_model": s.embed_model,
            "reviewer_enabled": s.reviewer_enabled,
            "max_exec_retries": s.max_exec_retries,
            "workspace_path": str(orch.workspace_path),
            "obsidian_vault": s.obsidian_vault_path or "-",
        },
        "storage": storage_backend,
        "counts": counts,
        "health": _health(orch),
    }


def _health(orch: AILabsOrchestrator) -> dict:
    s = orch.settings
    env_path = s.model_config.get("env_file") or (Path(__file__).resolve().parent.parent.parent / ".env")
    checks = []
    checks.append({"label": "File .env", "ok": bool(env_path and Path(env_path).exists())})
    checks.append(
        {
            "label": f"API key LLM ({s.llm_provider})",
            "ok": s.llm_provider == "mock"
            or (s.llm_provider == "gemini" and bool(s.gemini_api_key))
            or (s.llm_provider == "deepseek" and bool(s.deepseek_api_key)),
        }
    )
    checks.append(
        {
            "label": "Supabase terkonfigurasi",
            "ok": bool(
                s.supabase_url
                and (s.supabase_publishable_key or s.supabase_secret_key or s.supabase_anon_key)
            ),
        }
    )
    checks.append(
        {
            "label": "Backend storage",
            "ok": True,
            "note": "Supabase" if isinstance(orch.storage, SupabaseStorage) else "JSON lokal",
        }
    )
    checks.append(
        {
            "label": "Embedding (semantik)",
            "ok": isinstance(orch.embedder, SentenceTransformerEmbedder),
            "note": "aktif" if isinstance(orch.embedder, SentenceTransformerEmbedder) else "nonaktif (Noop)",
        }
    )
    try:
        ws = Path(orch.workspace_path)
        ws.mkdir(parents=True, exist_ok=True)
        writable = ws.is_dir()
    except OSError:
        writable = False
    checks.append({"label": "Workspace dapat ditulis", "ok": writable, "note": str(Path(orch.workspace_path))})
    return checks


def _event_log(orch: AILabsOrchestrator, state, job_id: str | None) -> list[dict]:
    """Gabungkan event lintas job; filter per job bila dipilih."""
    events: list[dict] = []
    with state.events_lock:
        for jid, buf in state.job_events.items():
            if job_id and jid != job_id:
                continue
            events.extend({"job_id": jid, "time": e["time"], "msg": e["msg"]} for e in buf)
    events.sort(key=lambda x: x["time"], reverse=True)
    return events[:300]


def _toggle_agent_config(name: str) -> bool:
    """Flip enabled di agent_config.yaml. Berlaku saat proses restart."""
    import yaml

    path = Settings().agent_config_path
    if not path.exists():
        raw = {"agents": {}}
    else:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    agents = raw.setdefault("agents", {})
    override = agents.setdefault(name, {})
    current = bool(override.get("enabled", True))
    override["enabled"] = not current
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return not current


def _guess_mime(path: Path) -> str:
    mapping = {
        ".md": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".py": "text/x-python; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json",
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".yaml": "text/yaml; charset=utf-8",
        ".yml": "text/yaml; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".svg": "image/svg+xml",
    }
    return mapping.get(path.suffix.lower(), "application/octet-stream")


app = create_app()
