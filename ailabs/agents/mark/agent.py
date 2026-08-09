"""Mark — CEO AI Labs. Orchestrator: pecah misi jadi task graph, assign tim, sintesis hasil."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.models.agent_result import AgentResult


class MarkAgent(BaseAgent):
    name = "mark"
    role = "CEO AI Labs"
    description = (
        "CEO. Menerima misi dari user, memecah jadi task list (JSON), "
        "menentukan dependency, mendelegasikan ke tim, dan menyusun laporan akhir."
    )

    def plan(self, user_prompt: str, roster: str) -> dict:
        user = (
            f"MISI DARI BOSS:\n{user_prompt}\n\n"
            f"TIM AI LABS:\n{roster}\n\n"
            "Buat rencana kerja dalam bentuk JSON (lihat instruksi di atas)."
        )
        return self.llm.generate_json(self.system_prompt(), user, temperature=0.2)

    def synthesize(self, job_prompt: str, tasks_summary: str) -> str:
        user = (
            f"MISI AWAL:\n{job_prompt}\n\n"
            f"RINGKASAN HASIL TIM:\n{tasks_summary}\n\n"
            "Susun laporan akhir (markdown) untuk boss."
        )
        return self.llm.generate(self.system_prompt(), user, temperature=0.4)

    def execute(self, task, context: str = "") -> AgentResult:
        return AgentResult(
            success=False,
            error="Mark tidak mengeksekusi task worker; dia hanya merencanakan & menyintesis.",
        )


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return MarkAgent(llm=llm, skills=skills, model=model)
