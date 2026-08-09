"""Renderer markdown kecil (subset aman) untuk dokumen plan/report.

Tanpa dependensi tambahan: escape HTML dulu, lalu ubah elemen dasar.
Tidak mengeksekusi HTML mentah dari konten.
"""

from __future__ import annotations

import html
import re

_BLOCK_QUOTE = re.compile(r"^( {0,3})&gt; ?(.*)$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_LIST_ITEM = re.compile(r"^ {0,3}([-*]|\d+[.)])\s+(.*)$")
_HORIZONTAL = re.compile(r"^ {0,3}([-*_]){3,}\s*$")
_CODE_LINE = re.compile(r"^ {0,3}(```.*)$")


def render_md(text: str) -> str:
    """Render markdown subset jadi HTML aman (dipakai template dengan |safe)."""
    if not text:
        return ""

    lines = text.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        if in_code:
            if stripped.startswith("```"):
                out.append(
                    f"<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>"
                    if code_buf
                    else "<pre><code></code></pre>"
                )
                code_buf = []
                in_code = False
            else:
                code_buf.append(raw)
            i += 1
            continue

        m = _FENCE.match(stripped)
        if m:
            close_list()
            code_buf = []
            in_code = True
            i += 1
            continue

        if not stripped:
            close_list()
            out.append("")
            i += 1
            continue

        m = _HEADING.match(stripped)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        m = _HORIZONTAL.match(stripped)
        if m:
            close_list()
            out.append("<hr>")
            i += 1
            continue

        m = _BLOCK_QUOTE.match(stripped)
        if m:
            close_list()
            out.append(f"<blockquote>{_inline(m.group(2))}</blockquote>")
            i += 1
            continue

        m = _LIST_ITEM.match(stripped)
        if m:
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        # paragraf gabung sampai baris kosong
        close_list()
        para = [raw]
        i += 1
        while i < len(lines) and lines[i].strip():
            if _LIST_ITEM.match(lines[i].strip()) or _FENCE.match(lines[i].strip()):
                break
            para.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(' '.join(x.strip() for x in para))}</p>")

    close_list()
    if in_code and code_buf:
        out.append(f"<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>")
    return "\n".join(x for x in out if x != "")


def _inline(text: str) -> str:
    """Inline formatting: bold, italic, inline code, links."""
    text = html.escape(text)
    # inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # links [label](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    # bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # italic
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text
