"""Dara — Desain / UI Agent. Merancang wireframe, style guide, dan layout.

Sebelum menghasilkan desain, Dara membaca skill `taste_design` (pedoman
anti-slop dari taste-skill v2) supaya output tidak jatuh ke default AI.
"""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult
from ailabs.skills.base import SkillResult


class DesignAgent(BaseAgent):
    name = "dara"
    role = "Desain / UI Agent"
    description = "Merancang UI/UX: wireframe, style guide, dan struktur layout yang rapi."

    def execute(self, task, context: str = "") -> AgentResult:
        user = self._build_prompt(task, context)

        taste = self.skills.get("taste_design") if self.skills else None
        if taste is not None:
            try:
                res = taste.run(part="distilled")
                if isinstance(res, SkillResult) and res.ok:
                    user += "\n\nPANDUAN TASTE DESAIN (IKUTI aturan ini):\n" + str(res.value)
            except Exception as exc:  # noqa: BLE001
                user += f"\n\n(taste_design gagal dimuat: {exc})"

        loop_result = self.try_agentic_loop(task, context)
        if loop_result is not None:
            return loop_result

        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))
        return self._to_result(text)


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return DesignAgent(llm=llm, skills=skills, model=model)
