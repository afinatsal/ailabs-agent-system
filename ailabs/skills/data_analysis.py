"""data_analysis — analisis data CSV/JSON memakai stdlib (tanpa pandas).

Memberi ringkasan: jumlah baris, kolom, nilai kosong per kolom, statistik
ringkas kolom numerik (min/max/mean/median), dan preview beberapa baris
pertama. Data besar cukup dibatasi jumlah baris yang diproses.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from ailabs.skills.base import Skill, SkillResult

_MISSING = {"", "NULL", "null", "nan", "None", "NA", "na"}
_MAX_ROWS = 5000


def _root(ctx: dict) -> Path:
    raw = ctx.get("workspace_path") or ""
    return (Path(raw).resolve() if raw else Path.cwd() / "workspace").resolve()


def _resolve_safe(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"path '{rel_path}' berada di luar workspace")
    return target


def _load_rows(target: Path):
    suffix = target.suffix.lower()
    if suffix == ".json":
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("data", data)
        rows = data if isinstance(data, list) else []
    elif suffix == ".csv":
        with target.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        return None
    return rows[:_MAX_ROWS]


def _to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"rows": 0, "columns": [], "stats": {}, "missing": {}, "preview": []}

    columns = list(rows[0].keys())
    preview = [dict(r) for r in rows[:5]]
    numeric: dict[str, list[float]] = {col: [] for col in columns}
    missing: dict[str, int] = {col: 0 for col in columns}
    for r in rows:
        for col in columns:
            val = r.get(col)
            if val is None or str(val).strip() in _MISSING:
                missing[col] = missing.get(col, 0) + 1
                continue
            num = _to_number(val)
            if num is not None:
                numeric[col].append(num)

    stats: dict[str, dict] = {}
    for col, vals in numeric.items():
        if len(vals) >= 2:
            item = {
                "count": len(vals),
                "min": min(vals),
                "max": max(vals),
                "mean": round(statistics.fmean(vals), 4),
                "median": statistics.median(vals),
            }
            stats[col] = item
        elif vals:
            stats[col] = {"count": 1, "value": vals[0]}

    return {
        "rows": len(rows),
        "columns": columns,
        "stats": stats,
        "missing": missing,
        "preview": preview,
    }


def analyze_data(path: str, **ctx) -> SkillResult:
    root = _root(ctx)
    try:
        target = _resolve_safe(root, path)
    except PermissionError as exc:
        return SkillResult(ok=False, error=str(exc))
    if not target.exists():
        return SkillResult(ok=False, error=f"file tidak ditemukan: {path}")

    rows = _load_rows(target)
    if rows is None:
        return SkillResult(
            ok=False, error=f"format tak didukung: {target.suffix} (pakai .csv/.json)"
        )
    return SkillResult(ok=True, value=_summarize(rows))


SKILLS = [
    Skill(
        name="data_analysis",
        description=(
            "Analisis data CSV/JSON di workspace. Argumen: path (relatif). "
            "Kembalikan ringkasan statistik + preview."
        ),
        fn=analyze_data,
        tags=["data", "analysis"],
    )
]
