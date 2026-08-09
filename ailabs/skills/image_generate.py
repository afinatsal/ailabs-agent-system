"""image_generate — buat gambar/ilustrasi untuk artefak agent.

Default offline: generate SVG ilustratif (gradient + ornamen) berdasarkan
prompt, jadi tetap bisa dipakai tanpa API key. Bila env `IMAGE_API_URL` dan
`IMAGE_API_KEY` diset, coba dulu API gambar (kontrak kompatibel fal.ai /
Replicate), lalu fallback ke SVG kalau gagal.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult

_PALETTES = [
    ("#6366f1", "#a855f7", "#ec4899"),  # indigo -> fuchsia -> pink
    ("#0ea5e9", "#06b6d4", "#34d399"),  # sky -> cyan -> emerald
    ("#f59e0b", "#f97316", "#ef4444"),  # amber -> orange -> red
    ("#10b981", "#84cc16", "#eab308"),  # emerald -> lime -> yellow
    ("#8b5cf6", "#6366f1", "#3b82f6"),  # violet -> indigo -> blue
]


def _root(ctx: dict) -> Path:
    raw = ctx.get("workspace_path") or ""
    return (Path(raw).resolve() if raw else Path.cwd() / "workspace").resolve()


def _resolve_safe(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"path '{rel_path}' berada di luar workspace")
    return target


def _palette(prompt: str):
    digest = int(hashlib.sha1(prompt.encode("utf-8")).hexdigest(), 16)
    return _PALETTES[digest % len(_PALETTES)]


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_svg(prompt: str, width: int, height: int) -> str:
    c1, c2, c3 = _palette(prompt)
    label = _escape(prompt.strip()[:80] or "Ilustrasi")
    circles = [
        (width * 0.15, height * 0.25, min(width, height) * 0.12),
        (width * 0.8, height * 0.75, min(width, height) * 0.18),
        (width * 0.7, height * 0.2, min(width, height) * 0.08),
    ]
    circle_tags = "\n".join(
        f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{color}" opacity="0.35"/>'
        for (x, y, r), color in zip(circles, (c1, c3, c2))
    )
    font_size = max(18, width // 24)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f"  <defs>\n"
        f'    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n'
        f'      <stop offset="0%" stop-color="{c1}"/>\n'
        f'      <stop offset="50%" stop-color="{c2}"/>\n'
        f'      <stop offset="100%" stop-color="{c3}"/>\n'
        f"    </linearGradient>\n"
        f"  </defs>\n"
        f'  <rect width="{width}" height="{height}" fill="url(#bg)"/>\n'
        f"  {circle_tags}\n"
        f'  <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="system-ui, sans-serif" font-size="{font_size}" font-weight="700" '
        f'fill="#ffffff" opacity="0.92">{label}</text>\n'
        f"</svg>\n"
    )


def _generate_via_api(api_url: str, api_key: str | None, prompt: str, width: int, height: int):
    try:
        import httpx

        payload = {
            "prompt": prompt,
            "image_size": f"{width}x{height}",
            "num_images": 1,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = httpx.post(api_url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("images", data.get("data", []))
        return items[0].get("url") if isinstance(items, list) and items else data.get("url")
    except Exception:  # noqa: BLE001
        return None


def generate_image(
    prompt: str,
    path: str = "img/banner.svg",
    width: int = 1200,
    height: int = 630,
    **ctx,
) -> SkillResult:
    root = _root(ctx)
    root.mkdir(parents=True, exist_ok=True)
    try:
        target = _resolve_safe(root, path)
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.suffix.lower() != ".svg":
        api_url = os.getenv("IMAGE_API_URL", "").strip()
        if api_url:
            image_url = _generate_via_api(
                api_url, os.getenv("IMAGE_API_KEY", "").strip() or None, prompt, width, height
            )
            if image_url:
                import httpx

                blob = httpx.get(image_url, timeout=60).content
                target.write_bytes(blob)
                return SkillResult(ok=True, value=str(target))
        return SkillResult(
            ok=False,
            error=(
                "image_generate butuh API gambar untuk format non-SVG. "
                "Set IMAGE_API_URL (+ IMAGE_API_KEY) di .env, atau minta path "
                "berakhiran .svg untuk mode offline."
            ),
        )

    target.write_text(_build_svg(prompt, width, height), encoding="utf-8")
    return SkillResult(ok=True, value=str(target))


SKILLS = [
    Skill(
        name="image_generate",
        description=(
            "Buat gambar/ilustrasi. Argumen: prompt, path (contoh 'img/banner.svg'), "
            "width, height. Default offline menghasilkan SVG; format lain butuh "
            "IMAGE_API_URL/IMAGE_API_KEY di .env."
        ),
        fn=generate_image,
        tags=["image", "design"],
    )
]
