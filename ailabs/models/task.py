from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"        # belum siap, nunggu dependency
    READY = "ready"            # dependency selesai, siap eksekusi
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class TaskSpec(BaseModel):
    """Task yang dikeluarkan CEO (sebelum disimpan ke DB)."""

    description: str
    agent_name: str
    depends_on: list[str] = Field(default_factory=list)  # referensi TaskSpec.id
    input: dict[str, Any] = Field(default_factory=dict)
    goals: list[str] = Field(default_factory=list)  # kriteria sukses KHUSUS task ini


class Task(TaskSpec):
    """Task hasil breakdown CEO — satu baris di tabel `tasks`."""

    id: str
    job_id: str
    status: str = TaskStatus.PENDING.value
    output: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    review_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
