"""Factory LLM client berdasarkan settings.llm_provider.

Provider baru: cukup tambah implementasi LLMClient + satu cabang di sini.
"""

from __future__ import annotations

from ailabs.config.settings import Settings
from ailabs.llm.base import LLMClient


def build_llm(settings: Settings | None = None) -> LLMClient:
    settings = settings or Settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "gemini":
        from ailabs.llm.gemini import GeminiClient

        return GeminiClient(api_key=settings.gemini_api_key, model=settings.default_model)

    if provider == "deepseek":
        from ailabs.llm.deepseek import DeepSeekClient

        return DeepSeekClient(api_key=settings.deepseek_api_key, model=settings.deepseek_model)

    if provider == "openai_compat":
        from ailabs.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient(
            api_key=settings.openai_compat_api_key,
            model=settings.openai_compat_model,
            base_url=settings.openai_compat_base_url,
        )

    if provider in ("mock", "test"):
        from ailabs.llm.mock import MockClient

        return MockClient(model=settings.default_model)

    raise ValueError(
        f"LLM_PROVIDER '{provider}' tidak dikenal. "
        "Pilihan: gemini | deepseek | openai_compat | mock"
    )
