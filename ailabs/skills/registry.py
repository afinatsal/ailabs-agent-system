"""Registry skill — auto-discovery dari folder skills/*.py.

Konvensi: tiap modul skill mengekspos variabel `SKILLS` berupa list[Skill].
Menambah skill baru = buat file di folder ini, tanpa ubah kode lain.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from ailabs.skills.base import Skill

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent


class SkillRegistry:
    def __init__(self, context: dict | None = None):
        self.context = context or {}
        self._skills: dict[str, Skill] = {}
        self._discover()

    def _discover(self) -> None:
        for module_file in sorted(_SKILLS_DIR.glob("*.py")):
            if module_file.name.startswith("_"):
                continue
            module_name = module_file.stem
            try:
                module = importlib.import_module(f"ailabs.skills.{module_name}")
                skills = getattr(module, "SKILLS", [])
                for skill in skills:
                    if not isinstance(skill, Skill):
                        continue
                    if skill.name in self._skills:
                        logger.warning("Skill duplikat: %s", skill.name)
                    skill.context = self.context  # bagikan referensi context registry
                    self._skills[skill.name] = skill
                    logger.info("Skill terdaftar: %s", skill.name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Gagal load skill '%s': %s", module_name, exc)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def names(self) -> list[str]:
        return sorted(self._skills)

    def inject_context(self, **kwargs) -> None:
        self.context.update(kwargs)

    def list_text(self) -> str:
        lines = [f"- {s.name}: {s.description}" for s in self.all()]
        return "\n".join(lines)
