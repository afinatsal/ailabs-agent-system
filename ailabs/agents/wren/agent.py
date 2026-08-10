"""Wren — Writer Agent. Menulis dokumen, laporan, dan konten."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult


class WriterAgent(BaseAgent):
    name = "wren"
    role = "Writer Agent"
    description = "Menulis dokumen, laporan, dan konten yang rapi & mudah dibaca."

    def execute(self, task, context: str = "") -> AgentResult:
        loop_result = self.try_agentic_loop(task, context)
        if loop_result is not None:
            return loop_result

        user = self._build_prompt(task, context)
        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))
        return AgentResult(success=True, text=text, output={"text": text})

    def write_narrative_plan(self, title: str, summary: str, tasks) -> str:
        """Buat markdown plan naratif dari task graph (dipakai planner)."""
        lines = [
            f"# {title}",
            "",
            "## Ringkasan",
            summary,
            "",
            "## Breakdown Task",
        ]
        for t in tasks:
            dep = f" (setelah {', '.join(t.depends_on)})" if t.depends_on else ""
            lines.append(f"- [ ] **{t.id}** → {t.agent_name}{dep}: {t.description}")
        return "\n".join(lines)


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return WriterAgent(llm=llm, skills=skills, model=model)
