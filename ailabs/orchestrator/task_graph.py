"""TaskGraph — schema hasil planning CEO (Mark) + validasi + render markdown.

Dependency dinyatakan antar task LOKAL (t1, t2, ...). Saat disimpan ke DB,
id lokal dipetakan ke UUID task.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ailabs.models.task import TaskSpec


class TaskGraph(BaseModel):
    title: str = ""
    summary: str = ""
    goals: list[str] = Field(default_factory=list)
    tasks: list[TaskSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "TaskGraph":
        valid_ids = {f"t{i}" for i in range(1, len(self.tasks) + 1)}
        for idx, t in enumerate(self.tasks, start=1):
            local_id = f"t{idx}"
            for dep in t.depends_on:
                if dep not in valid_ids:
                    raise ValueError(
                        f"Task {local_id} depends_on '{dep}' tidak dikenal "
                        f"(id valid: {sorted(valid_ids)})"
                    )
        edges = [
            (dep, f"t{i+1}")
            for i, t in enumerate(self.tasks)
            for dep in t.depends_on
        ]
        if _has_cycle(edges):
            raise ValueError("TaskGraph mengandung dependency cycle")
        return self

    def validate_agents(self, known_agents: set[str]) -> list[str]:
        """Return daftar agent_name yang tidak dikenal (kalau kosong = valid)."""
        return [t.agent_name for t in self.tasks if t.agent_name not in known_agents]

    def to_specs_with_local_ids(self) -> list[tuple[str, TaskSpec]]:
        """[(local_id, spec)] — local_id = t1, t2, dst."""
        return [(f"t{i+1}", t) for i, t in enumerate(self.tasks)]

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title or 'AI Labs — Rencana Kerja'}",
            "",
            "## Ringkasan",
            self.summary or "-",
            "",
        ]
        if self.goals:
            lines += ["## Tujuan (Goals)", ""]
            lines += [f"- {g}" for g in self.goals]
            lines.append("")
        lines += ["## Breakdown Task"]
        for idx, t in enumerate(self.tasks, start=1):
            dep = f" (setelah {', '.join(t.depends_on)})" if t.depends_on else ""
            lines.append(f"- [ ] **t{idx}** → `{t.agent_name}`{dep}: {t.description}")
        return "\n".join(lines)


def _has_cycle(edges: list[tuple[str, str]]) -> bool:
    """Deteksi cycle di DAG. edges = [(dep_task, task_that_needs_it)].

    Directed graph: dependee -> dependent. Kalau ada cycle = true.
    """
    adj: dict[str, list[str]] = {}
    for dep, node in edges:
        adj.setdefault(dep, []).append(node)
        adj.setdefault(node, [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for nxt in adj.get(node, []):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and visit(nxt):
                return True
        color[node] = BLACK
        return False

    for node in adj:
        if color.get(node, WHITE) == WHITE:
            if visit(node):
                return True
    return False
