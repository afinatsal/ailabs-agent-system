"""Klien OpenAI-compatible generic — untuk proxy lokal/cloud (mis. 9router/kuroko).

Menghubungi `{base_url}/chat/completions` dengan skema OpenAI. Base URL harus
sudah mencakup `/v1` (contoh: `http://localhost:20128/v1`).
"""

from __future__ import annotations

import httpx

from ailabs.llm.base import LLMClient, LLMError


class OpenAICompatClient(LLMClient):
    provider = "openai_compat"

    def __init__(
        self,
        api_key: str,
        model: str = "kr/auto",
        base_url: str = "",
    ):
        if not api_key:
            raise LLMError("OPENAI_COMPAT_API_KEY belum diset. Isi di file .env.")
        if not base_url:
            raise LLMError("OPENAI_COMPAT_BASE_URL belum diset. Isi di file .env.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens or 8192,
        }
        try:
            resp = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"OpenAI-compatible API error {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI-compatible API error: {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"Respon OpenAI-compatible tidak dikenali: {str(data)[:300]}"
            ) from exc
