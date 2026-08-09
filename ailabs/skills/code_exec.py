"""code_exec — jalankan kode Python di subprocess dengan timeout.

PERINGATAN: tool ini mengeksekusi kode di mesin lokal. Hanya aktif kalau
agent memutuskan memakainya, dan punya timeout. Untuk multi-tenant/production,
ganti dengan sandbox (Docker / E2B / Firecracker).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult


def run_python(code: str, timeout: int = 30, **ctx) -> dict:
    # Jalankan di folder project workspace (bila ada) supaya path relatif
    # (mis. index.html) merujuk ke file project, bukan CWD server.
    cwd = ctx.get("workspace_path") or None
    if cwd:
        Path(cwd).mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "TIMEOUT"}
    except Exception as exc:  # noqa: BLE001
        return {"returncode": -2, "stdout": "", "stderr": str(exc)}


def _run_python_skill(code: str, timeout: int = 30):
    return SkillResult(value=run_python(code, timeout=timeout))


SKILLS = [
    Skill(
        name="code_exec",
        description="Jalankan kode Python. Argumen: code, timeout.",
        fn=run_python,
        tags=["code", "sandbox"],
    )
]
