"""DeepSeek client via OpenAI-compatible API.

DeepSeek mengekspos endpoint OpenAI-compatible, jadi cukup httpx.
"""

from __future__ import annotations

import httpx

from ailabs.llm.base import LLMClient, LLMError

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekClient(LLMClient):
    provider = "deepseek"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = DEEPSEEK_BASE_URL,
    ):
        if not api_key:
            raise LLMError("DEEPSEEK_API_KEY belum diset. Isi di file .env.")
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
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"DeepSeek API error {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"DeepSeek API error: {exc}") from exc
        return data["choices"][0]["message"]["content"] or ""
