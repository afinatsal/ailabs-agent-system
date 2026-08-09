"""Isolasi workspace per project: workspace/<project-slug>/."""

from pathlib import Path

from ailabs.config.settings import Settings
from ailabs.db.base import InMemoryStorage
from ailabs.orchestrator import AILabsOrchestrator
from ailabs.utils import slugify


class FakeFileLLM:
    """Planner + worker yang membuat file hello.txt."""

    provider = "fake"

    def generate_json(self, system, user, **kw):
        return {
            "title": "Proyek A",
            "summary": "s",
            "tasks": [
                {
                    "id": "t1",
                    "description": "Buat file hello.txt",
                    "agent_name": "dev",
                    "depends_on": [],
                    "input": {},
                }
            ],
        }

    def generate(self, system, user, **kw):
        return "```file:hello.txt\nhalo dari AI Labs\n```"


def _build_ws(tmp_path) -> tuple[AILabsOrchestrator, Path]:
    settings = Settings(
        llm_provider="mock",
        supabase_url="",
        supabase_anon_key="",
        reviewer_enabled=False,
        local_workspace_path=str(tmp_path / "ws"),
        enable_opencode=False,
    )
    storage = InMemoryStorage()
    orch = AILabsOrchestrator(storage=storage, settings=settings)
    fake = FakeFileLLM()
    orch.llm = fake
    for agent in orch.registry.all():
        agent.llm = fake
    return orch, tmp_path / "ws"


def test_slugify():
    assert slugify("Project A") == "project-a"
    assert slugify("  Artikel Produktivitas 2026! ") == "artikel-produktivitas-2026"
    assert slugify("!!!") == "project"
    assert slugify("Halo Dunia", max_len=6) == "halo-d"


def test_files_in_project_folder(tmp_path):
    orch, ws = _build_ws(tmp_path)
    report = orch.ask("Buat file", project="Project A")
    assert report.job.project == "project-a"
    target = ws / "project-a" / "hello.txt"
    assert target.exists(), f"file harus di {target}"
    assert target.read_text() == "halo dari AI Labs"


def test_project_derived_from_plan_title(tmp_path):
    orch, ws = _build_ws(tmp_path)
    report = orch.ask("Buat file")  # tanpa --project
    assert report.job.project == "proyek-a"  # dari title "Proyek A"
    assert (ws / "proyek-a" / "hello.txt").exists()


def test_two_projects_isolated(tmp_path):
    orch, ws = _build_ws(tmp_path)
    r1 = orch.ask("Buat file", project="Project A")
    r2 = orch.ask("Buat file", project="Project B")
    assert (ws / "project-a" / "hello.txt").exists()
    assert (ws / "project-b" / "hello.txt").exists()
    # tiap project punya foldernya sendiri, file tidak tertimpa
    assert r1.job.project != r2.job.project
