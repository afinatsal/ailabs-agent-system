"""Registry agent — auto-discovery dari folder agents/*.

Aturan konvensi:
- setiap subfolder berisi agent.py yang mengekspos fungsi `create(llm, skills, settings)`
  yang mengembalikan instance BaseAgent.
- nama agent = nama subfolder (lowercase).

Menambah agent baru = buat folder baru. Tidak perlu ubah kode core.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from ailabs.agents.base import BaseAgent
from ailabs.config.settings import Settings
from ailabs.llm.base import LLMClient

logger = logging.getLogger(__name__)

_AGENTS_DIR = Path(__file__).parent


class AgentRegistry:
    def __init__(self, llm: LLMClient, skills=None, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.llm = llm
        self.skills = skills or {}
        self._agents: dict[str, BaseAgent] = {}
        self._config = self.settings.agent_config()
        self._discover()

    def _discover(self) -> None:
        for folder in sorted(_AGENTS_DIR.iterdir()):
            if not folder.is_dir() or folder.name.startswith("__"):
                continue
            agent_file = folder / "agent.py"
            if not agent_file.exists():
                continue
            name = folder.name
            override = self._config.agents.get(name)
            if override is not None and not override.enabled:
                logger.info("Agent '%s' dinonaktifkan di agent_config.yaml", name)
                continue
            try:
                module = importlib.import_module(
                    f"ailabs.agents.{name}.agent"
                )
                create_fn = getattr(module, "create", None)
                if not callable(create_fn):
                    logger.warning("agents/%s/agent.py tidak punya fungsi create()", name)
                    continue
                agent = create_fn(
                    llm=self.llm,
                    skills=self.skills,
                    settings=self.settings,
                    config=override,
                )
                if not isinstance(agent, BaseAgent):
                    raise TypeError("create() harus mengembalikan instance BaseAgent")
                agent.name = name
                self._agents[name] = agent
                logger.info("Agent terdaftar: %s (%s)", name, agent.role)
            except Exception as exc:  # noqa: BLE001
                logger.error("Gagal load agent '%s': %s", name, exc)

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name.lower())

    def all(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def names(self) -> list[str]:
        return sorted(self._agents)

    def roster(self) -> str:
        lines = [f"- {a.name} ({a.role}): {a.description}" for a in self.all()]
        return "\n".join(lines)
