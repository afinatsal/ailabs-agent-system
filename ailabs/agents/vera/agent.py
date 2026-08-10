"""Vera — Reviewer/QA Agent. Meninjau hasil worker sebelum dianggap selesai."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult, ReviewVerdict


class ReviewerAgent(BaseAgent):
    name = "vera"
    role = "Reviewer / QA Agent"
    description = "Meninjau hasil agent lain; menyetujui atau meminta revisi."

    def review(self, task, agent_result: AgentResult, evidence: str = "") -> ReviewVerdict:
        goals = task.input.get("goals") if task.input else None
        goals_text = ""
        if goals:
            goals_text = "\n".join(f"{i}. {g}" for i, g in enumerate(goals, start=1))
        user = (
            f"TASK YANG DIREVIEW:\n{task.description}\n"
            f"OLEH AGENT: {task.agent_name}\n"
            f"INPUT TASK: {task.input}\n\n"
            f"HASIL AGENT:\n{agent_result.text or agent_result.output}\n\n"
        )
        if evidence:
            user += (
                "\nISI FILE DARI WORKSPACE (BUKTI KERJA AGENT — gunakan ini "
                "untuk memverifikasi klaim, bukan hanya narasi teks):\n"
                f"{evidence}\n\n"
            )
        if goals_text:
            user += (
                "\nGOALS TASK (nilai terhadap goals KHUSUS task ini, SATU-SATU):\n"
                f"{goals_text}\n\n"
                "Feedback WAJIB menyebut status per goal, mis. "
                "'goal 1 OK; goal 2 gagal: kontras di bawah AA'. "
                "Nilai HANYA terhadap goals ini — jangan menghakimi "
                "kriteria yang bukan tanggung jawab task. "
            )
        user += "Keluarkan keputusan review dalam JSON (lihat instruksi)."
        try:
            data = self.llm.generate_json(self.system_prompt(), user, temperature=0.2)
        except LLMError as exc:
            return ReviewVerdict(approved=False, feedback=f"Review gagal: {exc}")
        return ReviewVerdict(
            approved=bool(data.get("approved", False)),
            feedback=str(data.get("feedback", "")),
            score=data.get("score"),
        )

    def execute(self, task, context: str = "") -> AgentResult:
        return AgentResult(
            success=False,
            error="Vera tidak mengeksekusi task; dia meninjau lewat metode review().",
        )


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return ReviewerAgent(llm=llm, skills=skills, model=model)
