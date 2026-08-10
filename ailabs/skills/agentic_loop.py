"""agentic_loop — agent berputar otonom: pikir -> tool -> amati -> ulang.

LLM memutuskan tool berikutnya (dari registry skill), sistem menjalankannya,
hasilnya dikembalikan sebagai konteks, dan berulang sampai LLM menyatakan
selesai ({"done": true}) atau batas iterasi tercapai. Ini memberi agent
kemampuan "bertindak sendiri" seperti agent CLI (mis. opencode) tanpa butuh
binary eksternal — cukup LLM + skill yang sudah ada.
"""

from __future__ import annotations

from ailabs.llm.base import LLMError
from ailabs.skills.base import Skill, SkillResult

DEFAULT_MAX_ITERATIONS = 8

_SYSTEM = """\
Kamu adalah agen yang menyelesaikan tugas dengan memanggil tool satu per satu.

TUGAS:
{task}

GOALS (kriteria sukses — berhenti setelah tercapai):
{goals}

TOOL TERSEDIA (nama: deskripsi):
{tools}

Aturan:
- Jawab HANYA satu objek JSON, tanpa teks lain.
- Untuk memanggil tool: {{"tool": "<nama>", "args": {{...}}}}
  Argumen harus cocok dengan deskripsi tool (wajib/menggunakan nama persis).
- Setelah mendapat hasil tool, baca dulu sebelum memutuskan langkah berikut.
- Jika tugas selesai / goals tercapai: {{"done": true, "summary": "<ringkasan>"}}
- Jangan memanggil tool yang tidak ada di daftar. Jika tool error, perbaiki
  argumennya lalu coba lagi, atau pilih tool lain yang lebih cocok.
- Jangan mengulang tool yang sama dengan hasil error yang sama berulang kali.
"""


def _tool_list(registry) -> str:
    lines = []
    for skill in registry.all():
        if skill.name == "agentic_loop":
            continue
        lines.append(f"- {skill.name}: {skill.description}")
    return "\n".join(lines) or "(tidak ada skill)"


def _result_text(result) -> str:
    if isinstance(result, SkillResult):
        if not result.ok:
            return f"ERROR: {result.error}"
        return _result_text(result.value)
    if isinstance(result, dict):
        return str(result)
    return str(result)


def agentic_loop(task, goals=None, max_iterations=None, **ctx) -> SkillResult:
    llm = ctx.get("llm")
    registry = ctx.get("skills")
    if llm is None:
        return SkillResult(ok=False, error="llm tidak tersedia di context (agentic_loop)")
    if registry is None:
        return SkillResult(ok=False, error="skills registry tidak tersedia di context (agentic_loop)")

    limit = max_iterations or ctx.get("agentic_max_iterations") or DEFAULT_MAX_ITERATIONS
    goals = list(goals or [])
    tools = _tool_list(registry)
    system = _SYSTEM.format(
        task=task,
        goals="\n- ".join(goals) if goals else "(tidak ada)",
        tools=tools,
    )

    transcript: list[str] = []
    tools_used: list[str] = []

    for i in range(1, int(limit) + 1):
        history = "\n".join(transcript) if transcript else "(belum ada aksi)"
        user = f"Riwayat sejauh ini:\n{history}\n\nPutuskan langkah berikutnya (JSON):"
        try:
            decision = llm.generate_json(system, user)
        except LLMError as exc:
            if not transcript:
                return SkillResult(
                    ok=False,
                    error=f"agentic_loop: LLM tidak mengembalikan keputusan JSON di langkah awal: {exc}",
                    value={"tools_used": tools_used, "iterations": i},
                )
            return SkillResult(
                ok=True,
                value={
                    "summary": f"{exc}\n\nHasil parsial:\n{history}",
                    "tools_used": tools_used,
                    "iterations": i,
                    "partial": True,
                },
            )

        if decision.get("done"):
            return SkillResult(
                ok=True,
                value={
                    "summary": decision.get("summary", "Selesai."),
                    "tools_used": tools_used,
                    "iterations": i,
                },
            )

        tool = decision.get("tool")
        args = decision.get("args") or {}
        skill = registry.get(tool) if tool else None
        if skill is None:
            transcript.append(f"[{i}] Tool tidak dikenal: {tool!r}")
            continue
        tools_used.append(tool)
        try:
            result = skill.run(**args)
        except Exception as exc:  # noqa: BLE001
            result = SkillResult(ok=False, error=str(exc))
        transcript.append(f"[{i}] {tool}{args} -> {_result_text(result)}")

    return SkillResult(
        ok=False,
        error=f"agentic_loop mencapai batas {limit} iterasi tanpa selesai",
        value={"tools_used": tools_used, "iterations": int(limit)},
    )


SKILLS = [
    Skill(
        name="agentic_loop",
        description=(
            "Jalankan loop otonom: LLM memutuskan tool berikutnya, tool "
            "dijalankan, hasilnya dikembalikan, berulang sampai selesai. "
            "Argumen: task (wajib), goals (opsional), max_iterations (opsional)."
        ),
        fn=agentic_loop,
        tags=["agent", "loop"],
    )
]
