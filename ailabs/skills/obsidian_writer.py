"""obsidian_writer — tulis dokumen markdown ke vault Obsidian lokal (opsional).

Vault path diambil dari OBSIDIAN_VAULT_PATH di .env. Kalau kosong, skill
menjadi no-op yang aman.
"""

from __future__ import annotations

import re
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult


def _safe_filename(title: str) -> str:
    return re.sub(r"[^\w\- ]", "", title).strip().replace(" ", "-")[:80]


def write_note(
    title: str,
    content: str,
    folder: str = "AI-Labs",
    **ctx,
) -> SkillResult:
    vault = ctx.get("obsidian_vault_path") or ""
    if not vault:
        return SkillResult(
            ok=False,
            error="OBSIDIAN_VAULT_PATH kosong. Set di .env untuk mengaktifkan.",
        )
    target_dir = Path(vault) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_safe_filename(title)}.md"
    target.write_text(content, encoding="utf-8")
    return SkillResult(ok=True, value=str(target))


SKILLS = [
    Skill(
        name="obsidian_writer",
        description="Tulis catatan markdown ke vault Obsidian. Argumen: title, content, folder.",
        fn=write_note,
        tags=["obsidian", "docs"],
    )
]
