"""fetch_url — ambil isi halaman web lengkap (teks), bukan cuma cuplikan.

Memakai httpx (sudah jadi dependency project) + BeautifulSoup untuk merapikan
teks. Mengembalikan dict {url, status_code, title, text} agar mudah
diserialisasi ke JSON.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from ailabs.skills.base import Skill

_DEFAULT_HEADERS = {
    "User-Agent": "AILabs-Fetch/1.0 (+research)",
    "Accept": "text/html,application/xhtml+xml",
}


def fetch_url(url: str, max_chars: int = 8000, timeout: int = 20, **ctx) -> dict:
    resp = httpx.get(
        url,
        headers=_DEFAULT_HEADERS,
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    return {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "title": title,
        "text": text[:max_chars],
    }


SKILLS = [
    Skill(
        name="fetch_url",
        description=(
            "Baca isi satu halaman web secara lengkap. Argumen: url, "
            "max_chars (opsional). Kembalikan teks halaman."
        ),
        fn=fetch_url,
        tags=["web", "research"],
    )
]
