"""opencode_code — delegasikan task koding ke agent opencode (CLI).

Memanggil `opencode run --format json` sebagai sub-process di folder project
workspace. opencode (agent CLI) menulis/membaca/mengedit file sendiri lalu
mengembalikan hasil. Output diparse dari JSON events menjadi ringkasan.

Config opencode dipakai dari konfigurasi global opencode (~/.config/opencode).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult

DEFAULT_TIMEOUT = 900  # opencode = sesi agent penuh, bisa lama


def _find_opencode() -> str | None:
    """Cari binary opencode: PATH dulu, fallback ~/.opencode/bin."""
    path = shutil.which("opencode")
    if path:
        return path
    home_bin = Path.home() / ".opencode" / "bin" / "opencode"
    return str(home_bin) if home_bin.exists() else None


def _json_events(text: str) -> list[dict]:
    """Parse output `--format json` (satu objek JSON per baris)."""
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _summarize(events: list[dict]) -> str:
    """Rangkum events: tool yang dipakai, file ditulis, dan jawaban akhir."""
    tools: list[str] = []
    files_written: list[str] = []
    final_parts: list[str] = []
    for ev in events:
        p = ev.get("part") or {}
        if ev.get("type") == "tool_use" and isinstance(p, dict):
            tool = p.get("tool")
            if tool:
                tools.append(str(tool))
            state = p.get("state") or {}
            inp = state.get("input") or {}
            fp = inp.get("filePath") if isinstance(inp, dict) else None
            if fp and tool == "write":
                files_written.append(str(fp))
        if ev.get("type") == "text" and isinstance(p, dict):
            t = p.get("text")
            if t:
                final_parts.append(str(t))
    summary = []
    if tools:
        summary.append("Tool yang dipakai: " + ", ".join(dict.fromkeys(tools)))
    if files_written:
        summary.append("File ditulis: " + ", ".join(files_written))
    if final_parts:
        summary.append("Jawaban akhir:\n" + "\n".join(final_parts)[-1500:])
    return "\n".join(summary) if summary else "(opencode tidak menghasilkan output)"



def opencode_code(task: str, timeout: int = DEFAULT_TIMEOUT, **ctx) -> SkillResult:
    """Jalankan opencode untuk task koding di folder project workspace.

    Argumen:
      task   — arahan/instruksi coding untuk opencode (wajib).
      timeout— batas waktu eksekusi (detik, default 900).
    """
    binary = _find_opencode()
    if binary is None:
        return SkillResult(
            ok=False,
            error=(
                "opencode tidak ditemukan di PATH maupun ~/.opencode/bin. "
                "Install dulu: `npm i -g opencode-ai`"
            ),
        )
    if not task.strip():
        return SkillResult(ok=False, error="argumen `task` kosong")

    if not ctx.get("enable_opencode"):
        return SkillResult(
            ok=False,
            error=(
                "integrasi opencode dinonaktifkan (ENABLE_OPENCODE=false). "
                "Aktifkan di .env untuk mendelegasikan task koding ke opencode."
            ),
        )

    cwd = ctx.get("workspace_path")
    if not cwd:
        return SkillResult(
            ok=False, error="workspace_path tidak tersedia di context skill"
        )
    Path(cwd).mkdir(parents=True, exist_ok=True)

    # Instruksi tambahan agar opencode fokus menyelesaikan task dengan file.
    prompt = (
        task
        + "\n\nSelesaikan task ini dengan benar. Tulis/edit file yang diminta "
        "di folder project ini. Jangan mengeluarkan teks berlebihan."
    )
    cmd = [
        binary, "run", "--format", "json", "--dir", str(cwd), prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SkillResult(
            ok=False, error=f"opencode melebihi batas waktu {timeout}s"
        )
    except FileNotFoundError as exc:
        return SkillResult(ok=False, error=f"gagal menjalankan opencode: {exc}")

    stdout = proc.stdout or ""
    stderr = (proc.stderr or "").strip()
    events = _json_events(stdout)
    summary = _summarize(events)

    if proc.returncode != 0:
        return SkillResult(
            ok=False,
            error=f"opencode exit {proc.returncode}: {stderr[:500] or summary}",
            value={"returncode": proc.returncode, "summary": summary},
        )
    if not events:
        return SkillResult(
            ok=False,
            error=f"output opencode tidak ter-parse: {stdout[-500:] or stderr[:300]}",
            value={"returncode": proc.returncode},
        )
    return SkillResult(
        ok=True,
        value={"returncode": proc.returncode, "summary": summary},
    )


SKILLS = [
    Skill(
        name="opencode_code",
        description=(
            "Delegasikan task koding ke agent opencode (menulis/mengedit file "
            "di project). Argumen: task (arahan coding, wajib), timeout."
        ),
        fn=opencode_code,
        tags=["code", "agent"],
    )
]
