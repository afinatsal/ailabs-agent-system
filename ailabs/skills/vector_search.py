"""vector_search — cari konteks memori dari dokumen job.

Butuh context berisi `storage`, `embedder`, dan `job_id` yang di-inject ke
SkillRegistry saat aplikasi dibangun.
"""

from __future__ import annotations

from ailabs.memory.vector_store import retrieve_context
from ailabs.skills.base import Skill


def vector_search(query: str, top_k: int = 3, job_id: str | None = None, **ctx) -> str:
    storage = ctx.get("storage")
    embedder = ctx.get("embedder")
    if storage is None:
        return "(vector_search tidak tersedia: storage belum di-inject)"
    return retrieve_context(storage, embedder, job_id or "", query, top_k=top_k)


SKILLS = [
    Skill(
        name="vector_search",
        description=(
            "Cari konteks memori dari dokumen project. Argumen: query, job_id."
        ),
        fn=vector_search,
        tags=["memory", "retrieval"],
    )
]
