"""Utilitas kecil bersama."""

from __future__ import annotations

import re


def slugify(text: str, max_len: int = 40, default: str = "project") -> str:
    """Ubah teks jadi nama folder yang aman (lowercase, spasi -> '-')."""
    s = re.sub(r"[^\w\s-]", "", (text or "").lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = s.strip("-")
    s = s[:max_len].rstrip("-")
    return s or default
