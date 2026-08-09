"""filesystem — baca/tulis file di folder workspace lokal.

Folder root diambil dari `local_workspace_path` di settings (default:
`<project>/workspace`). Keamanan: path dipaksa tetap di dalam root
(menolak path traversal seperti `../`).
"""

from __future__ import annotations

from pathlib import Path

from ailabs.skills.base import Skill, SkillResult


def _root(ctx: dict) -> Path:
    raw = ctx.get("workspace_path") or ""
    return (Path(raw).resolve() if raw else Path.cwd() / "workspace").resolve()


def _resolve_safe(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"path '{rel_path}' berada di luar workspace")
    return target


def write_file(path: str, content: str = "", **ctx) -> SkillResult:
    root = _root(ctx)
    root.mkdir(parents=True, exist_ok=True)
    try:
        target = _resolve_safe(root, path)
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return SkillResult(ok=True, value=str(target))


def read_file(path: str, **ctx) -> SkillResult:
    root = _root(ctx)
    try:
        target = _resolve_safe(root, path)
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    if not target.exists():
        return SkillResult(ok=False, error=f"file tidak ditemukan: {path}")
    return SkillResult(ok=True, value=target.read_text(encoding="utf-8"))


def list_files(rel: str = ".", **ctx) -> list[str]:
    root = _root(ctx)
    try:
        base = _resolve_safe(root, rel or ".")
    except PermissionError:
        return []
    if not base.exists() or not base.is_dir():
        return []
    return [str(p.relative_to(root)) for p in sorted(base.rglob("*")) if p.is_file()]


SKILLS = [
    Skill(
        name="write_file",
        description=(
            "Simpan file ke folder workspace lokal. Argumen: path (relatif, "
            "contoh 'produk/index.html'), content (isi file)."
        ),
        fn=write_file,
        tags=["filesystem", "output"],
    ),
    Skill(
        name="read_file",
        description="Baca isi file dari workspace. Argumen: path.",
        fn=read_file,
        tags=["filesystem"],
    ),
    Skill(
        name="list_files",
        description="Daftar file di workspace. Argumen: rel (opsional).",
        fn=list_files,
        tags=["filesystem"],
    ),
]
