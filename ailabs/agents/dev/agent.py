"""Dev — Code Agent. Implementasi & perbaikan kode.

Urutan eksekusi:
  Path A: `agentic_loop` — loop otonom memakai LLM sendiri (pikir -> tool ->
          amati -> ulang) sampai goals task tercapai. Menggantikan gaya "sekali
          tembak"; Dev bisa baca/edit/grep/test file sendiri seperti agent CLI.
  Path B: `opencode_code` — delegasikan ke agent opencode (menulis file sendiri).
  Path C: fallback — LLM menulis kode, lalu `code_exec` menguji.

Untuk task frontend, Dev juga membaca skill `taste_design` (pedoman anti-slop)
supaya output-nya kohesif dengan style-guide yang dibuat Dara.
"""

from __future__ import annotations

from ailabs.agents.base import BaseAgent
from ailabs.llm.base import LLMError
from ailabs.models.agent_result import AgentResult
from ailabs.skills.base import SkillResult

_FRONTEND_KEYWORDS = (
    "html", "css", "tailwind", "javascript", "landing", "frontend",
    "web", "desain", "ui", "halaman", "interface", "tampilan",
)


class CodeAgent(BaseAgent):
    name = "dev"
    role = "Code Agent"
    description = "Menulis, memperbaiki, dan menguji kode."

    @staticmethod
    def _is_frontend(task) -> bool:
        desc = f"{task.description} {task.input}".lower()
        return any(k in desc for k in _FRONTEND_KEYWORDS)

    def execute(self, task, context: str = "") -> AgentResult:
        tools_used: list[str] = []
        run_result = ""
        exec_skill = self.skills.get("code_exec")
        opencode_skill = self.skills.get("opencode_code") if self.skills else None

        user = self._build_prompt(task, context)

        if self._is_frontend(task) and self.skills is not None:
            taste = self.skills.get("taste_design")
            if taste is not None:
                try:
                    res = taste.run(part="distilled")
                    if isinstance(res, SkillResult) and res.ok:
                        user += "\n\nPANDUAN TASTE DESAIN (IKUTI aturan ini):\n" + str(res.value)
                except Exception as exc:  # noqa: BLE001
                    user += f"\n\n(taste_design gagal dimuat: {exc})"

        # Path A: loop otonom — Dev memutuskan tool sendiri memakai LLM.
        loop_result = self.try_agentic_loop(task, context, user=user)
        if loop_result is not None:
            return loop_result

        # Path B: delegasikan task koding ke agent opencode (menulis file sendiri).
        if opencode_skill is not None:
            try:
                oc = opencode_skill.run(task=user, timeout=900)
                if isinstance(oc, SkillResult) and oc.ok:
                    tools_used.append("opencode_code")
                    run_result = oc.value if isinstance(oc.value, dict) else {"summary": str(oc.value)}
                    return self._to_result(
                        str(run_result.get("summary", "")),
                        extra_tools=tools_used,
                        extra_output={"opencode_result": run_result},
                    )
                # opencode gagal (mis. dinonaktifkan / tidak ditemukan) -> fallback LLM
                run_result = {"opencode_error": getattr(oc, "error", "opencode gagal")}
            except Exception as exc:  # noqa: BLE001
                run_result = {"opencode_error": str(exc)}

        # Path C: fallback — LLM menulis kode, lalu code_exec menguji.
        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))

        if exec_skill is not None:
            code = self._extract_python(text)
            if code:
                try:
                    run_result = exec_skill.run(code=code, timeout=30)
                    tools_used.append("code_exec")
                except Exception as exc:  # noqa: BLE001
                    run_result = {"error": str(exc)}

        return self._to_result(
            text,
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
    return CodeAgent(llm=llm, skills=skills, model=model)
