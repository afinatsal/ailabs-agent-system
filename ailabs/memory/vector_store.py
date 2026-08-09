"""Memori semantik: embedding dokumen + retrieval.

Embedder default = Noop (tidak melakukan apa-apa) supaya aplikasi tetap jalan
tanpa download model. Aktifkan embedding dengan menginstall sentence-transformers;
factory akan memakainya otomatis.
"""

from __future__ import annotations

import logging

from ailabs.config.settings import Settings

logger = logging.getLogger(__name__)


class Embedder:
    """Abstraksi: teks -> vector (list[float]) atau None kalau tidak tersedia."""

    dims: int | None = None

    def embed(self, text: str) -> list[float] | None:
        raise NotImplementedError


class NoopEmbedder(Embedder):
    dims = None

    def embed(self, text: str) -> list[float] | None:
        return None


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Install sentence-transformers untuk mengaktifkan embedding."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dims = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float] | None:
        vec = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec.tolist()]


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or Settings()
    try:
        return SentenceTransformerEmbedder(settings.embed_model)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Embedding nonaktif (%s). Pakai NoopEmbedder — retrieval semantik mati, "
            "fallback ke teks biasa.", exc
        )
        return NoopEmbedder()


def retrieve_context(
    storage,
    embedder: Embedder,
    job_id: str,
    query: str,
    top_k: int = 3,
) -> str:
    """Ambil konteks paling relevan untuk sebuah task.

    Prioritas: (1) embedding vector search, (2) fallback teks ILIKE,
    (3) dokumen plan job tsb.
    """
    if isinstance(embedder, SentenceTransformerEmbedder):
        vec = embedder.embed(query)
        if vec is not None:
            matched = _vector_search(storage, vec, job_id, top_k)
            if matched:
                return "\n\n".join(matched)

    docs = storage.list_documents(job_id)
    if docs:
        return "\n\n".join(f"[{d.title}] {d.content}" for d in docs[:top_k])
    return ""


def _vector_search(storage, vec: list[float], job_id: str, top_k: int) -> list[str]:
    """Panggil RPC match_documents via Supabase; InMemoryStorage tak didukung."""
    rpc = getattr(storage, "_client", None)
    if rpc is None:
        return []
    try:
        rows = (
            rpc.rpc(
                "match_documents",
                {
                    "query_embedding": vec,
                    "match_count": top_k,
                    "filter_job_id": job_id,
                },
            )
            .execute()
            .data
        )
        return [f"[{r.get('title', '')}] {r.get('content', '')}" for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector search gagal: %s", exc)
        return []
