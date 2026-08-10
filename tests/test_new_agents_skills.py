"""Agent baru (dara/rio/qa) + skill baru (fetch_url, image_generate,
git_deploy, data_analysis, translation) — pengujian tanpa API key & tanpa
Supabase."""

from __future__ import annotations

import json
import subprocess

from ailabs.llm.mock import MockClient
from ailabs.models.task import Task
from ailabs.skills.base import SkillResult
from ailabs.skills.registry import SkillRegistry


def _task(**overrides):
    defaults = {
        "id": "t-x",
        "job_id": "job-x",
        "agent_name": "dara",
        "description": "Buat desain landing page.",
        "input": {"topic": "Ice Cream"},
        "depends_on": [],
    }
    defaults.update(overrides)
    return Task(**defaults)


# ---------- registrasi ----------


def test_new_agents_registered(orchestrator):
    names = orchestrator.registry.names()
    assert {"dara", "rio", "qa"}.issubset(names)


def test_new_skills_registered(orchestrator):
    names = orchestrator.skills.names()
    assert {
        "fetch_url",
        "image_generate",
        "git_commit",
        "git_deploy",
        "data_analysis",
        "translation",
        "opencode_code",
        "agentic_loop",
        "glob_files",
        "grep_files",
        "edit_file",
    }.issubset(names)


# ---------- agent dara (desain/ui) ----------


def test_dara_writes_design_files(orchestrator):
    agent = orchestrator.registry.get("dara")
    result = agent.execute(_task(agent_name="dara"))
    assert result.success
    files = result.output.get("files_written", [])
    assert any("style-guide" in f for f in files)
    assert any("wireframe" in f for f in files)


# ---------- agent rio (data analyst) ----------


def test_rio_runs_analysis_and_reports(orchestrator):
    agent = orchestrator.registry.get("rio")
    result = agent.execute(
        _task(agent_name="rio", description="Analisis data penjualan.csv")
    )
    assert result.success
    assert result.output.get("code_result"), "rio harus menjalankan code_exec"
    assert "code_exec" in result.tools_used


# ---------- agent qa (tester) ----------


def test_qa_passes_when_verification_ok(orchestrator):
    agent = orchestrator.registry.get("qa")
    result = agent.execute(_task(agent_name="qa", description="Uji hasil landing page"))
    assert result.success
    assert "PASS" in result.text
    assert "code_exec" in result.tools_used


def test_qa_fails_without_code_skill():
    agent = orchestrator_registry_qa_without_skills()
    result = agent.execute(_task(agent_name="qa"))
    assert not result.success
    assert result.error


def orchestrator_registry_qa_without_skills():
    from ailabs.agents.qa.agent import QaAgent

    return QaAgent(llm=MockClient(), skills=None)


# ---------- skill image_generate ----------


def test_image_generate_writes_svg(tmp_path):
    skills = SkillRegistry(context={"workspace_path": str(tmp_path)})
    res = skills.get("image_generate").run(
        prompt="Landing page es krim", path="img/banner.svg"
    )
    assert isinstance(res, SkillResult)
    assert res.ok
    target = tmp_path / "img" / "banner.svg"
    assert target.exists()
    assert "<svg" in target.read_text(encoding="utf-8")


# ---------- skill data_analysis ----------


def test_data_analysis_summarizes_csv(tmp_path):
    (tmp_path / "data.csv").write_text("nama,nilai\nA,10\nB,20\nC,30\n", encoding="utf-8")
    skills = SkillRegistry(context={"workspace_path": str(tmp_path)})
    res = skills.get("data_analysis").run(path="data.csv")
    assert isinstance(res, SkillResult)
    assert res.ok
    assert res.value["rows"] == 3
    assert res.value["stats"]["nilai"]["mean"] == 20.0
    assert res.value["missing"]["nilai"] == 0


def test_data_analysis_missing_file(tmp_path):
    skills = SkillRegistry(context={"workspace_path": str(tmp_path)})
    res = skills.get("data_analysis").run(path="tidak-ada.csv")
    assert isinstance(res, SkillResult)
    assert not res.ok


# ---------- skill translation ----------


def test_translation_uses_llm_context():
    skills = SkillRegistry(context={"llm": MockClient()})
    res = skills.get("translation").run(text="Halo", target_lang="en")
    assert isinstance(res, SkillResult)
    assert res.ok
    assert res.value


def test_translation_requires_llm():
    skills = SkillRegistry()
    res = skills.get("translation").run(text="Halo", target_lang="en")
    assert isinstance(res, SkillResult)
    assert not res.ok


# ---------- skill fetch_url (path error tanpa jaringan) ----------


def test_fetch_url_error_path():
    skills = SkillRegistry()
    res = skills.get("fetch_url").run(url="http://127.0.0.1:1/x", timeout=3)
    assert isinstance(res, SkillResult)
    assert not res.ok


# ---------- skill git_commit / git_deploy ----------


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "qa@test.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "QA"], cwd=repo, check=True)
    return repo


def test_git_commit_in_repo(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    skills = SkillRegistry()
    res = skills.get("git_commit").run(message="init", path=str(repo), push=False)
    assert isinstance(res, SkillResult)
    assert res.ok
    assert "commit" in res.value


def test_git_commit_no_change_is_noop(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    skills = SkillRegistry()
    skills.get("git_commit").run(message="init", path=str(repo), push=False)
    res = skills.get("git_commit").run(message="lagi", path=str(repo), push=False)
    assert isinstance(res, SkillResult)
    assert res.ok
    assert "tidak ada perubahan" in res.value


def test_git_deploy_without_remote(tmp_path):
    repo = _make_repo(tmp_path)
    skills = SkillRegistry()
    res = skills.get("git_deploy").run(path=str(repo))
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "remote" in res.error


# ---------- skill opencode_code ----------


def test_opencode_code_disabled_by_default(tmp_path):
    """Tanpa flag enable_opencode, skill menolak (tidak menjalankan opencode asli)."""
    skills = SkillRegistry(context={"workspace_path": str(tmp_path)})
    res = skills.get("opencode_code").run(task="Buat file test.txt")
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "dinonaktifkan" in (res.error or "")


def test_opencode_code_flag_reads_context(tmp_path):
    """Saat enable_opencode aktif, skill mencoba menjalankan opencode binary."""
    skills = SkillRegistry(
        context={"workspace_path": str(tmp_path), "enable_opencode": True}
    )
    res = skills.get("opencode_code").run(task="Buat file test.txt", timeout=5)
    assert isinstance(res, SkillResult)
    # binary tersedia atau tidak — yang penting tidak ada error "dinonaktifkan"
    assert "dinonaktifkan" not in (res.error or "")


def test_dev_falls_back_to_llm_without_opencode_flag(orchestrator):
    """Di mode mock (enable_opencode=False), dev tetap jalan via LLM + code_exec."""
    agent = orchestrator.registry.get("dev")
    result = agent.execute(_task(agent_name="dev", description="Buat script python"))
    assert result.success
    assert "opencode_code" not in result.tools_used


# ---------- skill agentic_loop ----------


class _DecisionLLM(MockClient):
    """LLM tiruan: mengembalikan urutan keputusan JSON untuk tiap iterasi."""

    def __init__(self, decisions):
        super().__init__()
        self._decisions = list(decisions)
        self._calls = 0

    def generate(self, system, user, **kwargs):
        if self._calls >= len(self._decisions):
            return '{"done": true, "summary": "habis"}'
        decision = self._decisions[self._calls]
        self._calls += 1
        return json.dumps(decision)


def test_agentic_loop_runs_tools_until_done(tmp_path):
    """Loop otonom memanggil tool sampai LLM menyatakan selesai."""
    llm = _DecisionLLM(
        [
            {"tool": "write_file", "args": {"path": "halo.txt", "content": "hai"}},
            {"done": True, "summary": "File halo.txt berhasil dibuat."},
        ]
    )
    skills = SkillRegistry(
        context={"workspace_path": str(tmp_path), "llm": llm, "skills": None}
    )
    # skills registry dipakai untuk lookup tool
    skills.inject_context(skills=skills)
    res = skills.get("agentic_loop").run(task="Buat file halo.txt", goals=["file ada"])
    assert isinstance(res, SkillResult)
    assert res.ok
    assert res.value["summary"] == "File halo.txt berhasil dibuat."
    assert res.value["tools_used"] == ["write_file"]
    assert (tmp_path / "halo.txt").read_text() == "hai"


def test_agentic_loop_stops_at_max_iterations(tmp_path):
    """Saat LLM tidak kunjung selesai, loop berhenti dengan error."""
    llm = _DecisionLLM([{"tool": "list_files", "args": {"rel": "."}}] * 10)
    skills = SkillRegistry(
        context={"workspace_path": str(tmp_path), "llm": llm, "skills": None}
    )
    skills.inject_context(skills=skills)
    res = skills.get("agentic_loop").run(
        task="Cari sesuatu", max_iterations=3
    )
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "iterasi" in (res.error or "")


def test_agentic_loop_requires_llm(tmp_path):
    """Tanpa LLM di context, skill menolak."""
    skills = SkillRegistry(context={"workspace_path": str(tmp_path), "skills": None})
    skills.inject_context(skills=skills)
    res = skills.get("agentic_loop").run(task="x")
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "llm" in (res.error or "")


def test_dev_uses_agentic_loop_when_decisions_ok(tmp_path):
    """Dev memakai Path A (agentic_loop) jika LLM mengembalikan keputusan JSON."""
    from ailabs.agents.dev.agent import create as dev_create
    from ailabs.config.settings import Settings

    llm = _DecisionLLM(
        [
            {"tool": "write_file", "args": {"path": "kode.py", "content": "print(1)"}},
            {"done": True, "summary": "Kode selesai."},
        ]
    )
    skills = SkillRegistry(
        context={"workspace_path": str(tmp_path), "llm": llm, "skills": None}
    )
    skills.inject_context(skills=skills)

    settings = Settings(llm_provider="mock", default_model="mock-model")
    agent = dev_create(llm=llm, skills=skills, settings=settings, config=None)
    result = agent.execute(
        _task(agent_name="dev", description="Buat script python")
    )
    assert result.success
    assert "agentic_loop" in result.tools_used
    assert "write_file" in result.tools_used
    assert (tmp_path / "kode.py").read_text() == "print(1)"


def test_all_agents_use_agentic_loop_when_available(tmp_path):
    """Setiap worker agent memakai agentic_loop (Path otonom) bila keputusan JSON."""
    from ailabs.agents.registry import AgentRegistry
    from ailabs.config.settings import Settings

    llm = _DecisionLLM(
        [
            {"tool": "write_file", "args": {"path": "hasil.md", "content": "ok"}},
            {"done": True, "summary": "Selesai."},
        ]
    )
    skills = SkillRegistry(
        context={"workspace_path": str(tmp_path), "llm": llm, "skills": None}
    )
    skills.inject_context(skills=skills)

    settings = Settings(llm_provider="mock", default_model="mock-model")
    registry = AgentRegistry(llm=llm, skills=skills, settings=settings)
    for name in ("dev", "rita", "rio", "wren", "dara", "qa"):
        agent = registry.get(name)
        result = agent.execute(
            _task(agent_name=name, description=f"Task untuk {name}")
        )
        assert result.success, f"{name} harus sukses"
        assert "agentic_loop" in result.tools_used, f"{name} harus memakai agentic_loop"
        assert (tmp_path / "hasil.md").read_text() == "ok"
