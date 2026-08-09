"""Goals (kriteria sukses), review per-goal, taste_design, dan memori lessons."""

from __future__ import annotations

import json

from ailabs.llm.mock import MockClient
from ailabs.models.agent_result import AgentResult
from ailabs.models.task import Task
from ailabs.orchestrator.task_graph import TaskGraph
from ailabs.skills.base import SkillResult


def _task(**overrides):
    defaults = {
        "id": "t-x",
        "job_id": "job-x",
        "agent_name": "dev",
        "description": "Buat landing page.",
        "input": {},
        "depends_on": [],
    }
    defaults.update(overrides)
    return Task(**defaults)


# ---------- goals ----------


def test_mock_plan_has_goals():
    raw = MockClient().generate("sys", "buat rencana kerja untuk landing page")
    data = json.loads(raw)
    assert data["goals"]
    assert isinstance(data["goals"], list)


def test_taskgraph_renders_goals():
    from ailabs.models.task import TaskSpec

    graph = TaskGraph(
        title="Misi",
        summary="ringkasan",
        goals=["kontras AA", "responsif mobile"],
        tasks=[TaskSpec(description="buat desain", agent_name="dara", depends_on=[])],
    )
    md = graph.to_markdown()
    assert "Tujuan (Goals)" in md
    assert "kontras AA" in md


def test_goals_per_task_in_input(orchestrator):
    job = orchestrator.submit("Landing page es krim.")
    tasks = orchestrator.tasks(job.id)
    assert tasks
    for t in tasks:
        goals = t.input.get("goals")
        assert goals, "tiap task harus membawa goals per-task"
        assert len(goals) >= 1
        assert goals != orchestrator.executor.storage.get_job(
            job.id
        ).user_prompt, "goals harus spesifik task, bukan seluruh misi"


def test_planner_does_not_inject_mission_goals(orchestrator):
    from ailabs.models.task import TaskSpec
    from ailabs.orchestrator.planner import Planner

    job = orchestrator.storage.create_job("misi tanpa per-task goals")
    planner = Planner(
        orchestrator.llm, orchestrator.registry, orchestrator.storage
    )
    graph = TaskGraph(
        title="Misi",
        summary="s",
        goals=["goal misi A", "goal misi B"],
        tasks=[
            TaskSpec(
                description="Task tanpa goals sendiri",
                agent_name="dev",
                depends_on=[],
                input={"topic": "x"},
            ),
        ],
    )
    specs = [t for _, t in graph.to_specs_with_local_ids()]
    stored = planner._persist(job, graph, specs)
    task_input = stored[0].input
    assert task_input.get("goals") == [], (
        "tanpa goals per-task, planner TIDAK menyalin goals misi ke input"
    )


def test_vera_review_reads_goals(orchestrator):
    vera = orchestrator.registry.get("vera")
    verdict = vera.review(
        _task(input={"goals": ["kontras AA", "responsif"]}),
        AgentResult(text="hasil desain"),
    )
    assert verdict.approved is True  # mock reviewer selalu approve


# ---------- taste_design ----------


def test_taste_design_skill_distilled(orchestrator):
    skill = orchestrator.skills.get("taste_design")
    assert skill is not None
    res = skill.run(part="distilled")
    assert isinstance(res, SkillResult)
    assert res.ok
    low = res.value.lower()
    assert "design read" in low or "anti" in low


def test_taste_design_skill_full(orchestrator):
    skill = orchestrator.skills.get("taste_design")
    res = skill.run(part="full")
    assert isinstance(res, SkillResult)
    assert res.ok
    assert len(res.value) > 5000


def test_dara_registered_with_taste(orchestrator):
    assert orchestrator.registry.get("dara") is not None
    dara = orchestrator.registry.get("dara")
    result = dara.execute(_task(agent_name="dara", description="Desain landing page."))
    assert result.success


# ---------- memori lessons ----------


def test_learnings_append_and_load(orchestrator):
    job = orchestrator.submit("Proyek memory.")
    task = _task(id="t1", job_id=job.id, agent_name="dev")
    orchestrator.executor._append_lesson(
        job, task, "goal 2 gagal: kontras tombol di bawah WCAG AA"
    )
    lessons = orchestrator.executor._load_learnings(job, "dev")
    assert "kontras" in lessons
    assert orchestrator.executor._load_learnings(job, "rita") == ""


def test_learnings_filtered_per_agent(orchestrator):
    job = orchestrator.submit("Proyek memory 2.")
    orchestrator.executor._append_lesson(
        job, _task(id="t1", job_id=job.id, agent_name="dara"), "palet beige membosankan"
    )
    orchestrator.executor._append_lesson(
        job, _task(id="t2", job_id=job.id, agent_name="dev"), "N+1 query terdeteksi"
    )
    assert "beige" in orchestrator.executor._load_learnings(job, "dara")
    assert "beige" not in orchestrator.executor._load_learnings(job, "dev")


# ---------- fix QA: cwd workspace ----------


def test_code_exec_runs_in_workspace_cwd(tmp_path):
    from ailabs.skills.code_exec import run_python

    (tmp_path / "probe.txt").write_text("halo", encoding="utf-8")
    res = run_python(
        "import os; print(os.path.exists('probe.txt'))",
        workspace_path=str(tmp_path),
    )
    assert res["returncode"] == 0
    assert "True" in res["stdout"]


def test_code_exec_without_cwd_ignores_workspace(tmp_path):
    from ailabs.skills.code_exec import run_python

    (tmp_path / "probe.txt").write_text("halo", encoding="utf-8")
    res = run_python(
        "import os; print(os.path.exists('probe.txt'))",
    )
    assert res["returncode"] == 0
    assert "False" in res["stdout"]


# ---------- fix desain: style-guide dara & taste utk dev ----------


def test_executor_injects_styleguide_for_frontend(orchestrator, tmp_path):
    slug = "proyek-sg"
    ws_dir = orchestrator.settings.local_workspace_path
    import os

    os.makedirs(f"{ws_dir}/{slug}/design", exist_ok=True)
    with open(f"{ws_dir}/{slug}/design/style-guide.md", "w", encoding="utf-8") as fh:
        fh.write("Palet Zinc+Emerald, font Outfit. Tanpa emoji.")
    job = orchestrator.submit("Buat landing page web.", project=slug)
    task = _task(id="t-x", job_id=job.id, agent_name="dev")
    style = orchestrator.executor._load_project_styleguide(job, task)
    assert "Zinc+Emerald" in style
    assert "WAJIB DIIKUTI" in style


def test_executor_skips_styleguide_for_non_frontend(orchestrator):
    job = orchestrator.submit("Analisis data penjualan.", project="data-proyek")
    task = _task(id="t-x", job_id=job.id, agent_name="rio")
    assert orchestrator.executor._load_project_styleguide(job, task) == ""


def test_dev_reads_taste_design_for_frontend(orchestrator):
    dev = orchestrator.registry.get("dev")
    assert dev._is_frontend(_task(description="Buat halaman web dengan tailwind"))
    assert not dev._is_frontend(_task(description="Tulis API backend di FastAPI"))
