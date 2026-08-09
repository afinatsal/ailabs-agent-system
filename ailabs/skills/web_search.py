"""web_search — cari di web via DuckDuckGo HTML (tanpa API key, best-effort).

Untuk production yang lebih stabil, ganti dengan Tavily/Bing/Serper API
(tinggal ubah fungsi `_search` di bawah, API skill tidak berubah).
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from ailabs.skills.base import Skill

_DDG_URL = "https://html.duckduckgo.com/html/"


def web_search(query: str, max_results: int = 5, **ctx) -> list[dict]:
    """Kembalikan list dict {title, url, snippet}."""
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    }
    resp = httpx.get(_DDG_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []
    for result in soup.select(".result")[:max_results]:
        link = result.select_one("a.result__a")
        snippet = result.select_one(".result__snippet")
        if not link:
            continue
        url = link.get("href", "")
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            url = m.group(1)
        results.append(
            {
                "title": link.get_text(strip=True),
                "url": url,
                "snippet": snippet.get_text(strip=True) if snippet else "",
            }
        )
    return results


SKILLS = [
    Skill(
        name="web_search",
        description="Cari informasi di internet. Argumen: query, max_results.",
        fn=web_search,
        tags=["search", "internet"],
    )
]
