from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

JOB_STATUSES = ("pending", "planning", "running", "done", "failed")


class Job(BaseModel):
    """Satu baris per misi/prompt dari user (tabel `jobs`)."""

    id: str
    user_prompt: str
    project: str | None = None
    status: str = "pending"
    created_by: str | None = None
    final_report: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "failed")


class JobCreate(BaseModel):
    user_prompt: str = Field(min_length=1)
    created_by: str | None = None
    project: str | None = None
