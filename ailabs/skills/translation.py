"""translation — terjemahkan teks antarbahasa via LLM.

Butuh `llm` di context skill (di-inject oleh orchestrator). Ditandai
`needs_llm=True` supaya jelas skill ini tidak deterministik.
"""

from __future__ import annotations

from ailabs.skills.base import Skill, SkillResult


def translate(
    text: str,
    target_lang: str = "en",
    source_lang: str | None = None,
    tone: str = "natural",
    **ctx,
) -> SkillResult:
    llm = ctx.get("llm")
    if llm is None:
        return SkillResult(
            ok=False,
            error="translation butuh llm di context (di-inject orchestrator)",
        )
    system = (
        f"Kamu adalah penerjemah profesional. Terjemahkan teks ke {target_lang} "
        f"dengan nada {tone}. Hanya keluarkan hasil terjemahan, tanpa penjelasan."
    )
    user = f"Teks sumber ({source_lang or 'auto'}):\n{text}"
    try:
        out = llm.generate(system, user, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        return SkillResult(ok=False, error=str(exc))
    return SkillResult(ok=True, value=out.strip())


SKILLS = [
    Skill(
        name="translation",
        description=(
            "Terjemahkan teks ke bahasa target. Argumen: text, target_lang "
            "(contoh 'en'/'id'), source_lang (opsional), tone (opsional)."
        ),
        fn=translate,
        needs_llm=True,
        tags=["translation", "llm"],
    )
]
