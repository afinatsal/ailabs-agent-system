"""Planner — otak CEO (Mark): pecah misi jadi TaskGraph lalu simpan ke DB."""

from __future__ import annotations

import logging

from ailabs.agents.registry import AgentRegistry
from ailabs.db.base import Storage
from ailabs.llm.base import LLMClient, LLMError
from ailabs.models.document import DocType, Document
from ailabs.models.job import Job
from ailabs.models.task import Task, TaskSpec
from ailabs.orchestrator.task_graph import TaskGraph
from ailabs.utils import slugify

logger = logging.getLogger(__name__)


class Planner:
    def __init__(self, llm: LLMClient, registry: AgentRegistry, storage: Storage):
        self.llm = llm
        self.registry = registry
        self.storage = storage

    def plan(self, job: Job) -> list[Task]:
        """Panggil Mark (CEO) -> TaskGraph -> insert tasks + dokumen plan."""
        ceo = self.registry.get("mark")
        if ceo is None:
            raise RuntimeError("Agent 'mark' tidak terdaftar di registry.")

        self.storage.update_job(job.id, status="planning")

        known = set(self.registry.names())
        attempt = 0
        graph: TaskGraph | None = None
        last_error = ""
        while attempt < 3:
            attempt += 1
            try:
                raw = ceo.plan(job.user_prompt, roster=self.registry.roster())
                graph = TaskGraph.model_validate(raw)
                unknown = graph.validate_agents(known)
                if unknown:
                    raise ValueError(
                        f"CEO merujuk agent tak dikenal: {unknown}. "
                        f"Gunakan: {sorted(known - {'mark'})}"
                    )
                break
            except (LLMError, ValueError) as exc:
                last_error = str(exc)
                logger.warning("Plan attempt %s gagal: %s", attempt, last_error)

        if graph is None:
            self.storage.update_job(
                job.id, status="failed", final_report=f"Planning gagal: {last_error}"
            )
            raise RuntimeError(f"Gagal membuat rencana: {last_error}")

        specs = [t for _, t in graph.to_specs_with_local_ids()]
        try:
            tasks = self._persist(job, graph, specs)
        except Exception as exc:  # noqa: BLE001
            self.storage.update_job(
                job.id, status="failed", final_report=f"Penyimpanan plan gagal: {exc}"
            )
            raise
        return tasks

    def _persist(self, job: Job, graph: TaskGraph, specs: list[TaskSpec]) -> list[Task]:
        import uuid as _uuid

        # 1. siapkan UUID klien dulu agar depends_on (id lokal) bisa dipetakan
        #    sebelum insert — satu bulk insert, tanpa pass update ulang.
        local_ids = [f"t{i}" for i in range(1, len(specs) + 1)]
        id_map = {lid: str(_uuid.uuid4()) for lid in local_ids}

        def _task_input(spec: TaskSpec) -> dict:
            # goals KEHUSUS task (dari CEO atau fallback field goals),
            # bukan seluruh goals misi — mencegah retry storm lintas-task.
            goals = spec.input.get("goals") or spec.goals
            return {**(spec.input or {}), "goals": goals}

        mapped_specs = [
            spec.model_copy(
                update={
                    "depends_on": [
                        id_map[d] for d in spec.depends_on if d in id_map
                    ],
                    "input": _task_input(spec),
                }
            )
            for spec in specs
        ]
        stored = self.storage.create_tasks(
            job.id, mapped_specs, ids=[id_map[lid] for lid in local_ids]
        )

        # 2. simpan plan naratif sebagai dokumen
        plan_md = graph.to_markdown()
        self.storage.create_document(
            Document(
                id="",  # storage mengisi default
                job_id=job.id,
                title=graph.title or "Plan Kerja",
                content=plan_md,
                doc_type=DocType.PLAN.value,
                agent="mark",
            )
        )

        # 3. tentukan slug project (folder workspace) kalau belum diset user
        if not job.project:
            self.storage.update_job(
                job.id, project=slugify(graph.title or job.user_prompt)
            )

        self.storage.update_job(job.id, status="running")
        return stored
