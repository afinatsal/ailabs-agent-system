import pytest

from ailabs.models.task import TaskSpec
from ailabs.orchestrator.task_graph import TaskGraph, _has_cycle


def _graph(tasks: list[dict]) -> TaskGraph:
    return TaskGraph(
        title="Test",
        summary="sum",
        tasks=[TaskSpec(**t) for t in tasks],
    )


def test_valid_dag():
    g = _graph(
        [
            {"description": "a", "agent_name": "rita", "depends_on": [], "input": {}},
            {"description": "b", "agent_name": "dev", "depends_on": ["t1"], "input": {}},
            {"description": "c", "agent_name": "wren", "depends_on": ["t2"], "input": {}},
        ]
    )
    assert len(g.tasks) == 3
    assert g.validate_agents({"rita", "dev", "wren", "mark"}) == []


def test_unknown_dependency():
    with pytest.raises(ValueError):
        _graph(
            [
                {"description": "a", "agent_name": "rita", "depends_on": ["t9"], "input": {}},
            ]
        )


def test_cycle_detected():
    with pytest.raises(ValueError):
        _graph(
            [
                {"description": "a", "agent_name": "rita", "depends_on": ["t2"], "input": {}},
                {"description": "b", "agent_name": "dev", "depends_on": ["t1"], "input": {}},
            ]
        )


def test_unknown_agent_reported():
    g = _graph(
        [
            {"description": "a", "agent_name": "ghost", "depends_on": [], "input": {}},
        ]
    )
    assert g.validate_agents({"rita", "dev"}) == ["ghost"]


def test_has_cycle_utility():
    assert _has_cycle([("a", "b"), ("b", "a")]) is True
    assert _has_cycle([("a", "b"), ("b", "c")]) is False
    assert _has_cycle([]) is False


def test_to_markdown():
    g = _graph(
        [
            {"description": "riset", "agent_name": "rita", "depends_on": [], "input": {}},
            {"description": "tulis", "agent_name": "wren", "depends_on": ["t1"], "input": {}},
        ]
    )
    md = g.to_markdown()
    assert "t1" in md and "rita" in md
    assert "(setelah t1)" in md
