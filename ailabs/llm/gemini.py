"""Gemini (Google AI) client — provider default.

Dokumentasi SDK: https://googleapis.github.io/python-genai/
"""

from __future__ import annotations

from ailabs.llm.base import LLMClient, LLMError


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite"):
        if not api_key:
            raise LLMError("GEMINI_API_KEY belum diset. Isi di file .env.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMError(
                "Paket 'google-genai' belum terinstall. Jalankan: pip install -r requirements.txt"
            ) from exc
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        config = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens or 8192,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                config=config,
                contents=user,
            )
        except Exception as exc:  # noqa: BLE001 — provider error bisa macam-macam
            raise LLMError(f"Gemini API error: {exc}") from exc
        return response.text or ""
