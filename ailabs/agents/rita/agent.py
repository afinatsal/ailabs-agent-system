"""Rita — Research Agent. Riset & pengumpulan informasi (pakai skill web_search)."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult


class ResearchAgent(BaseAgent):
    name = "rita"
    role = "Research Agent"
    description = "Riset: mencari informasi, menganalisis, dan merangkum temuan."

    def execute(self, task, context: str = "") -> AgentResult:
        tools_used: list[str] = []
        search_result = ""
        search_skill = self.skills.get("web_search")
        topic = task.input.get("topic") or task.description
        if search_skill is not None:
            try:
                results = search_skill.run(query=topic, max_results=5)
                tools_used.append("web_search")
                search_result = "\n".join(
                    f"- {r.get('title', '')}: {r.get('url', '')} — {r.get('snippet', '')}"
                    for r in results
                )
            except Exception as exc:  # noqa: BLE001
                search_result = f"(web_search gagal: {exc})"

        user = self._build_prompt(task, context)
        if search_result:
            user += f"\n\nHASIL PENCARIAN WEB:\n{search_result}"

        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))
        return self._to_result(
            text,
            extra_tools=tools_used,
            extra_output={"search_results": search_result},
        )


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return ResearchAgent(llm=llm, skills=skills, model=model)
