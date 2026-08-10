"""Qa — Tester Agent. Memverifikasi hasil kerja dev dan memberi laporan pengujian."""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult


class QaAgent(BaseAgent):
    name = "qa"
    role = "Tester Agent"
    description = "Menjalankan & memverifikasi hasil kerja dev; memberi laporan pengujian."

    def execute(self, task, context: str = "") -> AgentResult:
        loop_result = self.try_agentic_loop(task, context)
        if loop_result is not None:
            return loop_result

        tools_used: list[str] = []
        exec_skill = self.skills.get("code_exec") if self.skills else None

        user = self._build_prompt(task, context)
        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))

        passed = True
        run_result = ""
        code = self._extract_python(text)
        if code:
            if exec_skill is not None:
                try:
                    run_result = exec_skill.run(code=code, timeout=30)
                    tools_used.append("code_exec")
                    passed = run_result.get("returncode", 0) == 0
                except Exception as exc:  # noqa: BLE001
                    run_result = {"error": str(exc)}
                    passed = False
            else:
                passed = False
                run_result = {"error": "skill code_exec tidak tersedia"}
        else:
            passed = False
            run_result = {"error": "agent tidak menghasilkan kode pengujian yang bisa dijalankan"}

        report = (
            f"{text}\n\n## Laporan QA\n\n"
            f"- Status: {'PASS' if passed else 'FAIL'}\n"
            f"- Hasil eksekusi: {str(run_result)[:500]}"
        )
        if not passed:
            return AgentResult(
                success=False,
                text=report,
                output={"text": report, "code_result": run_result},
                tools_used=tools_used,
                error="Verifikasi QA gagal (returncode != 0).",
            )
        return self._to_result(
            report,
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
    return QaAgent(llm=llm, skills=skills, model=model)
