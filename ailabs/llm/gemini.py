"""Gemini (Google AI) client — provider default.

Dokumentasi SDK: https://googleapis.github.io/python-genai/
"""

from __future__ import annotations

import time

from ailabs.llm.base import LLMClient, LLMError

_RETRYABLE = (429, 500, 503)


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
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
        self._max_retries = max_retries
        self._retry_delay = retry_delay

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
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    config=config,
                    contents=user,
                )
                return response.text or ""
            except Exception as exc:  # noqa: BLE001 — provider error bisa macam-macam
                code = getattr(exc, "code", None)
                if isinstance(exc, self._types.HttpError):
                    code = exc.status_code
                if code in _RETRYABLE and attempt < self._max_retries:
                    time.sleep(self._retry_delay * (2**attempt))
                    last_error = exc
                    continue
                raise LLMError(f"Gemini API error: {exc}") from exc
        raise LLMError(f"Gemini API error setelah retry: {last_error}")
