"""Abstraksi LLM client supaya bisa ganti provider tanpa ubah kode agent.

Provider baru cukup implement `LLMClient` dan didaftarkan di `factory.py`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod


class LLMError(Exception):
    """Gagal memanggil LLM provider."""


def strip_json_fences(text: str) -> str:
    """Bersihkan ```json ... ``` dan teks di luar objek JSON pertama."""
    text = text.strip()
    if text.startswith("```"):
        first = text.find("\n")
        last = text.rfind("```")
        text = text[first + 1 : last] if last > first else text[3:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text.strip()


class LLMClient(ABC):
    provider: str = "base"

    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Kirim prompt, kembalikan teks jawaban."""

    def generate_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict:
        """Kirim prompt, harapkan jawaban JSON. Parsing dilakukan di sini."""
        raw = self.generate(
            system, user, temperature=temperature, max_tokens=max_tokens
        )
        try:
            return json.loads(strip_json_fences(raw))
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM tidak mengembalikan JSON yang valid: {exc}\n{raw[:500]}") from exc
