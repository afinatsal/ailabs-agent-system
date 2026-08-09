from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocType(str, Enum):
    PLAN = "plan"
    REPORT = "report"
    NOTE = "note"
    LOG = "log"


class Document(BaseModel):
    """Dokumen naratif (markdown) — tabel `documents`."""

    id: str
    job_id: str
    task_id: str | None = None
    title: str = ""
    content: str
    doc_type: str = DocType.PLAN.value
    agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
