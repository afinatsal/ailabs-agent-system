"""BaseAgent — semua worker agent (dan CEO) inherit dari sini.

Setiap agent punya:
- nama + role (dipakai planner & registry)
- system prompt (dibaca dari system_prompt.md di folder yang sama)
- akses ke LLM client
- akses ke skills registry (kemampuan reusable)
"""

from __future__ import annotations

import re
from pathlib import Path

from ailabs.llm.base import LLMClient, LLMError
from ailabs.models.agent_result import AgentResult
from ailabs.models.task import Task
from ailabs.skills.base import SkillResult

# Blok output file: ```file:rel/path\n<isi>\n```
FILE_BLOCK_RE = re.compile(r"```file:(.+?)\n(.*?)```", re.DOTALL)


class BaseAgent:
    name: str = "agent"
    role: str = "Agent"
    description: str = ""

    def __init__(
        self,
        llm: LLMClient,
        skills=None,
        model: str | None = None,
        extra_system_prompt: str = "",
    ):
        self.llm = llm
        self.skills = skills or {}
        self.model = model
        self.extra_system_prompt = extra_system_prompt

    # ---------- prompt ----------

    @property
    def prompt_path(self) -> Path:
        return Path(__file__).parent / self.name / "system_prompt.md"

    def system_prompt(self) -> str:
        prompt = ""
        if self.prompt_path.exists():
            prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        if self.extra_system_prompt:
            prompt = f"{prompt}\n\n{self.extra_system_prompt}".strip()
        return prompt

    def skill_descriptions(self) -> str:
        if not self.skills:
            return "(tidak ada skill)"
        lines = [f"- {s.name}: {s.description}" for s in self.skills.all()]
        return "\n".join(lines)

    # ---------- eksekusi ----------

    def execute(self, task: Task, context: str = "") -> AgentResult:
        """Implementasi generik: satu panggilan LLM. Worker bisa override."""
        user = self._build_prompt(task, context)
        try:
            text = self.llm.generate(self.system_prompt(), user)
        except LLMError as exc:
            return AgentResult(success=False, error=str(exc))
        return self._to_result(text)

    def _to_result(
        self,
        text: str,
        extra_tools: list[str] | None = None,
        extra_output: dict | None = None,
    ) -> AgentResult:
        """Bungkus output LLM jadi AgentResult; otomatis menulis file dari blok ```file:```."""
        written = self._write_file_blocks(text)
        if not written:
            written = self._materialize_code_blocks(text)
        output = {"text": text}
        if extra_output:
            output.update(extra_output)
        output = self._sanitize(output)
        tools = list(extra_tools or [])
        if written:
            output["files_written"] = written
            tools.append("write_file")
        return AgentResult(success=True, text=text, output=output, tools_used=tools)

    @staticmethod
    def _sanitize(value):
        """Ubah SkillResult (dan wadahnya) jadi struktur JSON-serializable."""
        if isinstance(value, SkillResult):
            return {"ok": value.ok, "value": value.value, "error": value.error}
        if isinstance(value, dict):
            return {k: BaseAgent._sanitize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [BaseAgent._sanitize(v) for v in value]
        return value

    def parse_file_blocks(self, text: str) -> list[tuple[str, str]]:
        return [
            (m.group(1).strip(), m.group(2).rstrip("\n"))
            for m in FILE_BLOCK_RE.finditer(text)
        ]

    _LANG_TO_FILE = {
        "html": "index.html",
        "htm": "index.html",
        "css": "style.css",
        "js": "script.js",
        "javascript": "script.js",
        "python": "main.py",
        "py": "main.py",
        "json": "data.json",
        "sql": "query.sql",
        "md": "README.md",
    }

    def _materialize_code_blocks(self, text: str) -> list[str]:
        """Cadangan saat agent tak memakai blok ```file:```: tulis blok kode yang
        ditemukan ke file sesuai bahasa agar hasil tetap muncul di workspace."""
        written: list[str] = []
        skill = self.skills.get("write_file") if self.skills else None
        if skill is None:
            return written
        used: set[str] = set()
        for m in re.finditer(r"```([A-Za-z0-9_-]*)\n(.*?)```", text, re.DOTALL):
            filename = self._LANG_TO_FILE.get(m.group(1).strip().lower())
            if not filename:
                continue
            base, ext = filename.rsplit(".", 1)
            candidate, n = filename, 2
            while candidate in used:
                candidate = f"{base}-{n}.{ext}"
                n += 1
            used.add(candidate)
            result = skill.run(path=candidate, content=m.group(2).rstrip("\n"))
            if isinstance(result, SkillResult):
                if result.ok and result.value:
                    written.append(str(result.value))
            elif result:
                written.append(str(result))
        return written

    def _write_file_blocks(self, text: str) -> list[str]:
        """Tulis file yang diminta agent (lewat blok ```file:```) ke workspace."""
        written: list[str] = []
        skill = self.skills.get("write_file") if self.skills else None
        if skill is None:
            return written
        for rel_path, content in self.parse_file_blocks(text):
            result = skill.run(path=rel_path, content=content)
            if isinstance(result, SkillResult):
                if result.ok and result.value:
                    written.append(str(result.value))
            elif result:
                written.append(str(result))
        return written

    def _build_prompt(self, task: Task, context: str) -> str:
        parts = [
            f"TUGAS: {task.description}",
            f"DIPETIK OLEH: {self.role}",
            f"DARI BOSS (CEO): laporan misi = {task.job_id}",
        ]
        if task.input:
            parts.append(f"PARAMETER TAMBAHAN: {task.input}")
        if context:
            parts.append(f"\nKONTEKS:\n{context}")
        if self.skills:
            parts.append(f"\nSKILL YANG TERSEDIA:\n{self.skill_descriptions()}")
        parts.append(
            "\nKALAU TUGAS MENGARAHKAN MEMBUAT FILE, pakai skill write_file: "
            "tulis satu blok per file, diawali tiga backtick lalu kata 'file:' "
            "dan path relatif ke folder workspace, pindah baris, isi file, lalu "
            "tiga backtick penutup. Jangan menulis contoh placeholder."
        )
        return "\n\n".join(parts)

    def try_agentic_loop(
        self, task: Task, context: str = "", user: str | None = None
    ) -> AgentResult | None:
        """Jalankan task lewat skill `agentic_loop` (loop otonom) bila tersedia.

        Worker agent bisa memanggil ini di awal `execute()`. Mengembalikan
        `None` kalau skill tidak ada / gagal di langkah awal, sehingga agent
        tetap bisa memakai jalur eksekusi lamanya (fallback).
        """
        skill = self.skills.get("agentic_loop") if self.skills else None
        if skill is None:
            return None
        goals = list(task.goals or [])
        if isinstance(task.input, dict):
            goals = list(task.input.get("goals", [])) + goals
        if user is None:
            user = self._build_prompt(task, context)
        try:
            loop = skill.run(task=user, goals=goals)
        except Exception:  # noqa: BLE001
            return None
        if not (isinstance(loop, SkillResult) and loop.ok):
            return None
        value = loop.value if isinstance(loop.value, dict) else {}
        loop_tools = list(value.get("tools_used", []))
        return self._to_result(
            str(value.get("summary", "")),
            extra_tools=["agentic_loop", *loop_tools],
            extra_output={"agentic_loop_result": value},
        )
