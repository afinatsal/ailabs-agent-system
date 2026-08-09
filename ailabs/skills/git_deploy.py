"""git_deploy — commit & deploy hasil kerja ke git.

Best-effort: butuh `git` (dan `gh` untuk GitHub Pages) terinstall di mesin.
Menyasar repo di folder workspace project atau path yang diberikan secara
eksplisit. Skill ini tidak pernah membocorkan output mentah ke log.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd)
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git/gh tidak terinstall"
    except subprocess.TimeoutExpired:
        return -2, "", "TIMEOUT"


def _repo_path(path: str | None, ctx: dict) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    raw = ctx.get("workspace_path") or ""
    return (Path(raw).resolve() if raw else Path.cwd() / "workspace").resolve()


def git_commit(
    message: str = "Auto commit AI Labs",
    path: str | None = None,
    push: bool = False,
    branch: str | None = None,
    **ctx,
) -> SkillResult:
    repo = _repo_path(path, ctx)
    if not repo.exists():
        return SkillResult(ok=False, error=f"repo tidak ditemukan: {repo}")

    rc, out, err = _run(["git", "-C", str(repo), "status", "--porcelain"], repo)
    if rc != 0:
        return SkillResult(ok=False, error=f"bukan repo git: {err or out}")
    if not out.strip():
        return SkillResult(ok=True, value="tidak ada perubahan untuk di-commit")

    _run(["git", "-C", str(repo), "add", "-A"], repo)
    rc, out, err = _run(["git", "-C", str(repo), "commit", "-m", message], repo)
    if rc != 0:
        return SkillResult(ok=False, error=f"commit gagal: {err or out}")

    if push:
        cmd = ["git", "-C", str(repo), "push"]
        if branch:
            cmd += ["origin", branch]
        rc, out, err = _run(cmd, repo)
        if rc != 0:
            return SkillResult(ok=False, error=f"push gagal: {err or out}")

    return SkillResult(ok=True, value=f"commit '{message}' di {repo}")


def git_deploy(
    path: str | None = None,
    message: str = "Deploy AI Labs",
    target: str = "gh-pages",
    **ctx,
) -> SkillResult:
    repo = _repo_path(path, ctx)
    if not repo.exists():
        return SkillResult(ok=False, error=f"repo tidak ditemukan: {repo}")

    rc, out, err = _run(["git", "-C", str(repo), "remote", "get-url", "origin"], repo)
    if rc != 0:
        return SkillResult(ok=False, error=f"tidak ada remote origin: {err or out}")

    rc, out, err = _run(["git", "-C", str(repo), "push", "origin", f"HEAD:{target}"], repo)
    if rc == 0:
        return SkillResult(ok=True, value=f"deploy ke branch {target} berhasil")

    rc2, out2, err2 = _run(["gh", "pages", "deploy"], repo)
    if rc2 == 0:
        return SkillResult(ok=True, value="deploy GitHub Pages berhasil (gh pages deploy)")

    return SkillResult(
        ok=False,
        error=f"deploy gagal (push: {err or out}; fallback gh: {err2 or out2})",
    )


SKILLS = [
    Skill(
        name="git_commit",
        description=(
            "Commit perubahan ke repo git. Argumen: message, path (opsional), "
            "push (bool), branch (opsional)."
        ),
        fn=git_commit,
        tags=["git", "deploy"],
    ),
    Skill(
        name="git_deploy",
        description=(
            "Deploy hasil kerja ke branch (default gh-pages). Argumen: path, "
            "message, target."
        ),
        fn=git_deploy,
        tags=["git", "deploy"],
    ),
]
