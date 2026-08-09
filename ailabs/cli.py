"""CLI AI Labs — interaksi dengan Mark & tim lewat terminal.

Contoh:
    ailabs ask "Riset topik X dan tulis ringkasannya"
    ailabs submit "Buat landing page sederhana"
    ailabs run <job_id>
    ailabs status <job_id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def _fmt_time(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def _print_job(job) -> None:
    print(f"\nJob ID     : {job.id}")
    print(f"Project    : {job.project or '-'}")
    print(f"Status     : {job.status}")
    print(f"Prompt     : {job.user_prompt}")
    print(f"Created by : {job.created_by or '-'}")
    print(f"Created at : {_fmt_time(job.created_at)}")
    print(f"Updated at : {_fmt_time(job.updated_at)}")


def _print_tasks(tasks) -> None:
    if not tasks:
        print("  (tidak ada task)")
        return
    print(f"{'ID':<12} {'STATUS':<11} {'AGENT':<8} DESCRIPTION")
    print("-" * 78)
    for t in tasks:
        dep = f"[{','.join(d[:8] for d in t.depends_on)}]" if t.depends_on else ""
        print(
            f"{t.id[:12]:<12} {t.status:<11} {t.agent_name:<8} "
            f"{t.description[:45]} {dep}"
        )


def _build_orchestrator(on_event=None, *, allow_mock_fallback: bool = False):
    """Bangun orchestrator; tangani key LLM yang belum diset dengan ramah.

    allow_mock_fallback=True → perintah read-only (agents/status/dst) tetap jalan
    memakai mock LLM walaupun API key belum ada.
    """
    from ailabs.config.settings import Settings
    from ailabs.llm.base import LLMError
    from ailabs.orchestrator import AILabsOrchestrator

    try:
        orch = AILabsOrchestrator(on_event=on_event)
    except LLMError as exc:
        if not allow_mock_fallback:
            print(f"[!] {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"[i] {exc}\n    Memakai mock LLM untuk perintah ini.\n", file=sys.stderr)
        settings = Settings(llm_provider="mock")
        orch = AILabsOrchestrator(on_event=on_event, settings=settings)

    if orch.settings.llm_provider.lower() == "mock":
        print(
            "[i] LLM_PROVIDER=mock — output adalah placeholder, tanpa API key.\n"
            "    Set LLM_PROVIDER=gemini + GEMINI_API_KEY di .env untuk hasil nyata.\n"
        )
    return orch


def cmd_ask(args) -> int:
    orch = _build_orchestrator(on_event=lambda m, _j: print(f"  • {m}"))
    print(f"\n>> Memberi misi ke {orch.settings.agent_config().ceo_name} (AI Labs):")
    print(f'   "{args.prompt}"\n')
    report = orch.ask(args.prompt, created_by=args.by, project=args.project)
    _print_job(report.job)
    print("\nTasks:")
    _print_tasks(orch.tasks(report.job.id))
    print("\n--- Laporan Akhir ---")
    print(report.job.final_report or "(tidak ada)")
    return 0


def cmd_submit(args) -> int:
    orch = _build_orchestrator(on_event=lambda m, _j: print(f"  • {m}"))
    print(f"\n>> Mengirim misi & meminta {orch.settings.agent_config().ceo_name} merencanakan...\n")
    job = orch.submit(args.prompt, created_by=args.by, project=args.project)
    _print_job(job)
    print("\nRencana (tasks):")
    _print_tasks(orch.tasks(job.id))
    print(f"\nJalankan eksekusi: ailabs run {job.id}")
    return 0


def cmd_run(args) -> int:
    orch = _build_orchestrator(on_event=lambda m, _j: print(f"  • {m}"))
    report = orch.run(args.job_id)
    print(f"\nJob {args.job_id} -> {report.job.status}")
    print(f"  tasks done   : {report.tasks_done}")
    print(f"  tasks failed : {report.tasks_failed}")
    print(f"  revisions    : {report.revisions}")
    return 0


def cmd_status(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    job = orch.status(args.job_id)
    if job is None:
        print(f"Job {args.job_id} tidak ditemukan.")
        return 1
    _print_job(job)
    print("\nTasks:")
    _print_tasks(orch.tasks(args.job_id))
    return 0


def cmd_tasks(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    _print_tasks(orch.tasks(args.job_id))
    return 0


def cmd_report(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    job = orch.status(args.job_id)
    if job is None:
        print(f"Job {args.job_id} tidak ditemukan.")
        return 1
    print(job.final_report or "(belum ada laporan — job belum selesai)")
    return 0


# ---------- operasional dashboard / maintenance ----------


def cmd_jobs(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    jobs = orch.all_jobs(limit=args.limit)
    if not jobs:
        print("Belum ada job.")
        return 0
    print(f"{'ID':<14} {'STATUS':<9} {'PROJECT':<12} {'TASKS':>5} {'CREATED':<16} PROMPT")
    print("-" * 96)
    for j in jobs:
        tasks = orch.tasks(j.id)
        done = sum(1 for t in tasks if t.status == "done")
        print(
            f"{j.id[:14]:<14} {j.status:<9} {(j.project or '-'):<12} "
            f"{done}/{len(tasks):<3} {_fmt_time(j.created_at):<16} {j.user_prompt[:40]}"
        )
    return 0


def cmd_logs(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    log = orch.skill_log()
    if not log:
        print("Belum ada aktivitas skill.")
        return 0
    print(f"{'WAKTU':<19} {'SKILL':<14} {'OK':<4} ERROR")
    print("-" * 90)
    for entry in log:
        ok = "ya" if entry["ok"] else "TIDAK"
        err = entry.get("error") or "-"
        print(f"{_fmt_time(entry['time']):<19} {entry['skill']:<14} {ok:<4} {err[:60]}")
    return 0


def cmd_retry(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    task = orch.retry_task(args.task_id)
    if task is None:
        print(f"Task {args.task_id} tidak ditemukan.")
        return 1
    print(f"Task {task.id[:12]} -> {task.status}")
    print(f"  agent : {task.agent_name}")
    print(f"  desc  : {task.description}")
    print(f"  run ulang: ailabs run {task.job_id}")
    return 0


def cmd_cancel(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    job = orch.cancel_job(args.job_id)
    if job is None:
        print(f"Job {args.job_id} tidak ditemukan.")
        return 1
    print(f"Job {job.id} dibatalkan. Status: {job.status}")
    return 0


def cmd_delete(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    if args.job_id != "ALL" and not args.yes:
        confirm = input(f"Hapus job {args.job_id} beserta task & dokumennya? [y/N] ")
        if confirm.lower() not in ("y", "yes"):
            print("Dibatalkan.")
            return 0
    if args.job_id == "ALL":
        jobs = orch.all_jobs()
        if not jobs:
            print("Belum ada job.")
            return 0
        if not args.yes:
            confirm = input(f"Hapus SEMUA {len(jobs)} job? [y/N] ")
            if confirm.lower() not in ("y", "yes"):
                print("Dibatalkan.")
                return 0
        for j in jobs:
            orch.delete_job(j.id)
        print(f"Menghapus {len(jobs)} job.")
        return 0
    ok = orch.delete_job(args.job_id)
    print(f"Job {args.job_id} dihapus." if ok else f"Job {args.job_id} tidak ditemukan.")
    return 0 if ok else 1


def cmd_clear(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    if not args.yes:
        confirm = input("Hapus SEMUA job, task, dan dokumen? [y/N] ")
        if confirm.lower() not in ("y", "yes"):
            print("Dibatalkan.")
            return 0
    orch.clear_all()
    print("Semua data telah dihapus.")
    return 0


def cmd_agents(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    print(f"\nTim AI Labs (CEO: {orch.settings.agent_config().ceo_name}):\n")
    print(orch.roster())
    print()
    return 0


def cmd_skills(args) -> int:
    orch = _build_orchestrator(allow_mock_fallback=True)
    print("\nSkill terdaftar:\n")
    print(orch.skills.list_text())
    print()
    return 0


def cmd_init(args) -> int:
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / ".env.example"
    dst = Path(__file__).resolve().parent.parent / ".env"
    if dst.exists():
        print(f".env sudah ada: {dst}")
    else:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f".env dibuat dari template: {dst}\nIsi GEMINI_API_KEY + SUPABASE_URL/SUPABASE_ANON_KEY.")
    print("\nLangkah berikutnya:")
    print("  1. pip install -r requirements.txt")
    print("  2. Jalankan db/schema.sql di Supabase SQL editor (buat schema 'ailabs')")
    print("  3. Isi GEMINI_API_KEY + SUPABASE_URL + salah satu key Supabase di .env")
    print("  4. ailabs agents  (cek tim sudah terdaftar)")
    return 0


def cmd_serve(args) -> int:
    """Jalankan dashboard web (FastAPI + uvicorn)."""
    import uvicorn

    host, port = args.host, args.port
    print(f"\nAI Labs Control Room → http://{host}:{port}")
    print("  Ctrl+C untuk berhenti.\n")
    uvicorn.run("ailabs.dashboard:app", host=host, port=port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ailabs",
        description="AI Labs — perusahaan multi-agent. Beri misi ke Mark (CEO).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ask", help="Kirim misi, Mark rencanakan + tim kerjakan + laporan.")
    p.add_argument("prompt", help="Misi / prompt untuk AI Labs")
    p.add_argument("--by", default=None, help="Identitas pengirim (opsional)")
    p.add_argument(
        "--project",
        default=None,
        help="Nama project — hasil file disimpan di workspace/<project>/ (opsional)",
    )
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("submit", help="Kirim misi & minta Mark membuat rencana saja.")
    p.add_argument("prompt", help="Misi / prompt untuk AI Labs")
    p.add_argument("--by", default=None, help="Identitas pengirim (opsional)")
    p.add_argument(
        "--project",
        default=None,
        help="Nama project — hasil file disimpan di workspace/<project>/ (opsional)",
    )
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("run", help="Eksekusi job yang sudah direncanakan.")
    p.add_argument("job_id", help="ID job")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="Lihat status job + task list.")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("tasks", help="Lihat task list sebuah job.")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("report", help="Tampilkan laporan akhir job.")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_report)

    sub.add_parser("agents", help="Daftar anggota tim AI Labs.").set_defaults(func=cmd_agents)
    sub.add_parser("skills", help="Daftar skill yang tersedia.").set_defaults(func=cmd_skills)
    sub.add_parser("init", help="Buat .env dari template + panduan setup.").set_defaults(func=cmd_init)

    p = sub.add_parser("jobs", help="Operasional: daftar semua job + ringkasan task.")
    p.add_argument("--limit", type=int, default=50, help="Jumlah job maksimal (default 50)")
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("logs", help="Operasional: lihat aktivitas skill (session ini).")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("retry", help="Operasional: ulangi task yang gagal.")
    p.add_argument("task_id", help="ID task yang statusnya 'failed'")
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("cancel", help="Operasional: batalkan job yang belum selesai.")
    p.add_argument("job_id", help="ID job")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("delete", help="Operasional: hapus job beserta task & dokumennya.")
    p.add_argument("job_id", help="ID job, atau 'ALL' untuk semua")
    p.add_argument("--yes", action="store_true", help="Lewati konfirmasi")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("clear", help="Operasional: hapus semua data (job, task, dokumen).")
    p.add_argument("--yes", action="store_true", help="Lewati konfirmasi")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("serve", help="Jalankan dashboard web (Control Room).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="Auto-reload saat kode berubah (dev)")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
