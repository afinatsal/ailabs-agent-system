"""Rio — Data Analyst Agent. Membaca & menganalisis data, lalu merangkum."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult


class DataAnalystAgent(BaseAgent):
    name = "rio"
    role = "Data Analyst"
    description = "Menganalisis data (CSV/JSON), menghitung statistik, dan menulis laporan data."

    def execute(self, task, context: str = "") -> AgentResult:
        tools_used: list[str] = []
        run_result = ""
        exec_skill = self.skills.get("code_exec") if self.skills else None
        base = self._build_prompt(task, context)

        try:
            code_text = self.llm.generate(
                self.system_prompt(),
                base
                + "\n\nTULIS KODE: susun kode Python untuk memuat data di workspace "
                "dan mencetak ringkasan (jumlah baris, kolom, statistik ringkas). "
                "Keluarkan kode dalam fenced block ```python```.",
            )
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))

        code = self._extract_python(code_text)
        if code and exec_skill is not None:
            try:
                run_result = exec_skill.run(code=code, timeout=60)
                tools_used.append("code_exec")
            except Exception as exc:  # noqa: BLE001
                run_result = {"error": str(exc)}

        try:
            summary = self.llm.generate(
                self.system_prompt(),
                base
                + "\n\nHASIL ANALISIS DATA:\n"
                + str(run_result)
                + "\n\nBuat laporan singkat dalam markdown dengan angka konkret; "
                "sertakan blok file untuk laporan bila relevan.",
            )
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))

        return self._to_result(
            summary,
            extra_tools=tools_used,
            extra_output={"code_result": run_result},
        )

    @staticmethod
    def _extract_python(text: str) -> str:
        if "```python" in text:
            body = text.split("```python", 1)[1]
            if "```" in body:
                return body.split("```", 1)[0].strip()
        return ""


def create(llm, skills=None, settings=None, config=None):
    model = (config.model if config else None) or settings.default_model
    return DataAnalystAgent(llm=llm, skills=skills, model=model)
