"""
Vector store implementations for the RAG pipeline.

Design decision: the DATABASE (DocumentEmbedding.embedding_vector, a JSON
column — see app/models/system.py) is the source of truth for vector VALUES,
not a separately-persisted FAISS/Chroma index file. Both vector stores below
are built IN-MEMORY, on demand, from whatever chunks a query call passes in
(usually "every chunk for this stock" or "every chunk across all documents").
This avoids a dual-source-of-truth sync problem (index file vs. DB rows
disagreeing after an edit/delete) at the cost of rebuilding the index on
every query — a real, explicitly-documented trade-off that's fine at the
chunk counts a demo/portfolio-scale system will see, and the first thing a
production scale-up would change (persist + incrementally update the index
instead of rebuilding it).
"""
import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class SearchResult:
    id: str
    score: float  # cosine similarity, higher is more relevant
    metadata: dict


class VectorStore(ABC):
    @abstractmethod
    def build(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        """(Re)builds the index from scratch with the given vectors."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class FAISSVectorStore(VectorStore):
    """
    Exact (brute-force) nearest-neighbor search via faiss.IndexFlatIP.
    Vectors are expected to already be L2-normalized (every EmbeddingModel in
    app/rag/embeddings.py guarantees this), which makes inner product exactly
    equal to cosine similarity — IndexFlatIP is the correct, simplest choice
    for that, with no approximation (IVF/HNSW) needed at this scale.
    """

    def __init__(self):
        self._index = None
        self._ids: list[str] = []
        self._metadatas: list[dict] = []
        self._dimension: int | None = None

    def build(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        import faiss

        if len(ids) != len(vectors) or len(ids) != len(metadatas):
            raise ValueError("ids, vectors, and metadatas must be the same length")

        self._ids = list(ids)
        self._metadatas = list(metadatas)
        if len(vectors) == 0:
            self._index = None
            self._dimension = None
            return

        vectors = np.ascontiguousarray(vectors.astype(np.float32))
        self._dimension = vectors.shape[1]
        self._index = faiss.IndexFlatIP(self._dimension)
        self._index.add(vectors)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []
        query = np.ascontiguousarray(query_vector.reshape(1, -1).astype(np.float32))
        top_k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # faiss pads with -1 if top_k > ntotal in some versions
                continue
            results.append(SearchResult(id=self._ids[idx], score=float(score), metadata=self._metadatas[idx]))
        return results


_CHROMA_CLIENT = None  # process-wide singleton -- see _get_chroma_client() docstring


def _get_chroma_client():
    """
    Returns a single, process-wide chromadb client, created once, backed by
    a temp directory on disk (PersistentClient) rather than
    chromadb.EphemeralClient()'s purely in-memory SQLite.

    This matters for correctness, not just efficiency. Two real, observed
    failure modes drove this design:

    1. EphemeralClient() instantiated repeatedly within one long-running
       process (a pytest session, or a real API server handling many
       requests, both are exactly that) intermittently corrupted its own
       internal tenant/database bookkeeping ("no such table: tenants").
    2. Even with a single EphemeralClient instance shared across calls, its
       purely in-memory (":memory:") SQLite connection is NOT safely shared
       across threads the way a real file is — and FastAPI's TestClient runs
       request handling in a worker thread distinct from wherever the client
       was first created, which reproduced as "no such table: collections"
       (a fresh, schema-less in-memory DB being seen from a different
       thread/connection context than the one that created the schema).

    A temp-directory-backed PersistentClient sidesteps both: it's created
    once, and being a real file on disk, is naturally consistent across
    threads/connections the way :memory: databases are not.
    """
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        import tempfile

        import chromadb
        from chromadb.config import Settings

        persist_dir = tempfile.mkdtemp(prefix="stockvision_chroma_")
        _CHROMA_CLIENT = chromadb.PersistentClient(path=persist_dir, settings=Settings(anonymized_telemetry=False))
    return _CHROMA_CLIENT


class ChromaDBVectorStore(VectorStore):
    """
    Alternative backend using chromadb's embedded (no-server) client.

    Design decision: embeddings are always passed explicitly to
    `collection.add(embeddings=...)` / `.query(query_embeddings=...)` — never
    left for Chroma to compute via its own default embedding function, which
    would silently try to download a sentence-transformers model from the
    Hugging Face Hub on first use (unavailable in this sandbox, and a hidden
    dependency in any network-restricted deployment). Every vector Chroma
    stores here came from an app.rag.embeddings.EmbeddingModel, same as FAISS.
    """

    def __init__(self, collection_name: str = "stockvision_rag"):
        self._collection_name = collection_name
        self._collection = None

    def build(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        client = _get_chroma_client()
        # Rebuilding: delete-then-recreate the collection rather than upsert,
        # since `build()`'s contract (see VectorStore ABC) is "replace the
        # whole index", not "merge into it".
        # `suppress` rather than try/except/pass: identical behaviour, but it
        # states "this failure is expected and ignored" as an assertion instead
        # of as an empty block a reader has to interpret. The expected failure is
        # a missing collection on the very first build.
        with contextlib.suppress(Exception):
            client.delete_collection(self._collection_name)
        self._collection = client.create_collection(self._collection_name)

        if len(ids) == 0:
            return
        # Chroma rejects a metadata dict with zero keys outright (a
        # backend-specific validation quirk FAISS has no equivalent of) --
        # substitute a harmless placeholder key rather than let that leak
        # into every caller of the shared VectorStore interface.
        safe_metadatas = [m if m else {"_empty": True} for m in metadatas]
        self._collection.add(
            ids=[str(i) for i in ids],
            embeddings=vectors.astype(np.float32).tolist(),
            metadatas=safe_metadatas,
        )

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self._collection is None or self._collection.count() == 0:
            return []
        top_k = min(top_k, self._collection.count())
        result = self._collection.query(query_embeddings=[query_vector.astype(np.float32).tolist()], n_results=top_k)
        results = []
        for id_, distance, metadata in zip(result["ids"][0], result["distances"][0], result["metadatas"][0]):
            # Chroma's default space is L2 distance, not cosine similarity;
            # since our vectors are L2-normalized, cosine_sim = 1 - (L2_dist^2 / 2)
            # is the exact conversion, keeping SearchResult.score comparable
            # across both vector store backends.
            similarity = 1 - (distance / 2)
            results.append(SearchResult(id=id_, score=float(similarity), metadata=metadata))
        return results


def new_vector_store(backend: str = "faiss") -> VectorStore:
    if backend == "faiss":
        return FAISSVectorStore()
    if backend == "chromadb":
        return ChromaDBVectorStore()
    raise ValueError(f"Unknown vector store backend '{backend}'. Use 'faiss' or 'chromadb'.")
