"""Fixtures bersama untuk tests — tanpa API key, tanpa Supabase."""

from __future__ import annotations

import pytest

from ailabs.config.settings import Settings
from ailabs.db.base import InMemoryStorage
from ailabs.orchestrator import AILabsOrchestrator


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_provider="mock",
        supabase_url="",
        supabase_anon_key="",
        reviewer_enabled=True,
        local_workspace_path=str(tmp_path / "ws"),
        enable_opencode=False,
    )


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def orchestrator(settings, storage):
    return AILabsOrchestrator(storage=storage, settings=settings)
