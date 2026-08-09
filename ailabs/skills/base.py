"""Skill = kemampuan/tool reusable yang bisa dipakai lintas agent.

Beda dengan agent: skill tidak punya LLM call sendiri (kecuali `needs_llm`),
scope-nya satu aksi konkret (cari web, jalankan kode, tulis file, dst).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SkillResult:
    ok: bool = True
    value: Any = None
    error: str | None = None


@dataclass
class Skill:
    name: str
    description: str
    fn: Callable[..., Any]
    needs_llm: bool = False
    tags: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    def run(self, **kwargs) -> Any:
        """Jalankan skill. Context registry otomatis digabung dengan argumen."""
        try:
            merged = {**self.context, **kwargs}
            result = self.fn(**merged)
            ok = not (isinstance(result, SkillResult) and not result.ok)
            self._record(ok=ok, error=None if ok else getattr(result, "error", None))
            return result
        except Exception as exc:  # noqa: BLE001
            self._record(ok=False, error=str(exc))
            return SkillResult(ok=False, error=str(exc))

    def _record(self, *, ok: bool, error: str | None) -> None:
        from datetime import datetime, timezone

        log = self.context.get("_skill_log")
        if log is None:
            return
        log.append(
            {
                "skill": self.name,
                "ok": ok,
                "error": error,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
