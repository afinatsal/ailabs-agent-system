from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Hasil eksekusi satu task oleh worker agent."""

    success: bool = True
    text: str = ""
    output: dict[str, Any] = Field(default_factory=dict)
    tools_used: list[str] = Field(default_factory=list)
    error: str | None = None


class ReviewVerdict(BaseModel):
    """Verdict Vera (Reviewer/QA) atas hasil worker."""

    approved: bool = False
    feedback: str = ""
    score: float | None = None
