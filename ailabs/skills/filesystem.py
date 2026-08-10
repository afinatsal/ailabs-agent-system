"""filesystem — baca/tulis/cari/edit file di folder workspace lokal.

Folder root diambil dari `local_workspace_path` di settings (default:
`<project>/workspace`). Keamanan: path dipaksa tetap di dalam root
(menolak path traversal seperti `../`).
"""

from __future__ import annotations

import re
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


def glob_files(pattern: str, **ctx) -> SkillResult:
    root = _root(ctx)
    root.mkdir(parents=True, exist_ok=True)
    try:
        matches = [str(p.relative_to(root)) for p in sorted(root.glob(pattern)) if p.is_file()]
    except Exception as exc:  # noqa: BLE001
        return SkillResult(ok=False, error=f"pola glob tidak valid: {exc}")
    return SkillResult(ok=True, value=matches)


def grep_files(pattern: str, rel: str = ".", **ctx) -> SkillResult:
    """Cari pola regex dalam isi file di workspace, kembalikan file:baris."""
    root = _root(ctx)
    try:
        base = _resolve_safe(root, rel or ".")
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    if not base.exists():
        return SkillResult(ok=False, error=f"folder tidak ditemukan: {rel}")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return SkillResult(ok=False, error=f"regex tidak valid: {exc}")
    hits: list[str] = []
    files = [base] if base.is_file() else [p for p in sorted(base.rglob("*")) if p.is_file()]
    for file in files:
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                rel_path = str(file.relative_to(root))
                hits.append(f"{rel_path}:{lineno}: {line.strip()[:200]}")
    if not hits:
        return SkillResult(ok=False, error=f"tidak ada hasil untuk pola '{pattern}'")
    return SkillResult(ok=True, value="\n".join(hits))


def edit_file(path: str, old: str, new: str, **ctx) -> SkillResult:
    """Ganti kemunculan `old` dengan `new` di dalam file workspace."""
    root = _root(ctx)
    try:
        target = _resolve_safe(root, path)
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    if not target.exists():
        return SkillResult(ok=False, error=f"file tidak ditemukan: {path}")
    text = target.read_text(encoding="utf-8")
    if old not in text:
        return SkillResult(ok=False, error=f"teks lama tidak ditemukan di {path}")
    if text.count(old) > 1:
        return SkillResult(
            ok=False,
            error=f"teks lama ditemukan {text.count(old)}x di {path}; "
            "berikan konteks yang lebih unik",
        )
    target.write_text(text.replace(old, new), encoding="utf-8")
    return SkillResult(ok=True, value=str(target))


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
    Skill(
        name="glob_files",
        description=(
            "Cari file sesuai pola glob (mis. '**/*.html'). Argumen: pattern."
        ),
        fn=glob_files,
        tags=["filesystem"],
    ),
    Skill(
        name="grep_files",
        description=(
            "Cari pola regex dalam isi file workspace; hasil 'path:baris: teks'. "
            "Argumen: pattern, rel (folder awal, opsional)."
        ),
        fn=grep_files,
        tags=["filesystem"],
    ),
    Skill(
        name="edit_file",
        description=(
            "Edit sebagian isi file: ganti `old` dengan `new` (harus unik). "
            "Argumen: path, old, new."
        ),
        fn=edit_file,
        tags=["filesystem"],
    ),
]
