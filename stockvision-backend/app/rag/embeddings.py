"""
Embedding models for the RAG pipeline.

Design decision — why HashingEmbedding, not a neural sentence-transformer,
is the DEFAULT: a typical sentence-transformer model needs its pretrained
weights downloaded from the Hugging Face Hub on first use. This sandbox (and
potentially some production deployments with locked-down egress) has no
network path to huggingface.co, so silently depending on that download
happening would make the "default" embedding path untestable here and
fragile there. HashingVectorizer (scikit-learn) needs no fitting and no
downloaded weights at all — it maps text to a fixed-dimension vector via the
hashing trick, deterministically and instantly, which makes it a genuinely
real, offline-safe default rather than a stand-in for something better.

Trade-off, stated plainly: hashed bag-of-words vectors capture LEXICAL
overlap (shared terms like "EBITDA", "revenue", a specific ticker) well, but
not deep semantic similarity the way a neural embedding would ("profit" and
"earnings" won't be recognized as related unless they co-occur). OpenAIEmbedding
below is the real upgrade path once network egress + an API key are available
— same EmbeddingModel interface, so swapping it in is a one-line config
change (see app/services/rag_service.py's get_embedding_model()).
"""
from abc import ABC, abstractmethod

import httpx
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer


class EmbeddingModel(ABC):
    name: str
    dimension: int

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Returns an (n_texts, dimension) float32 array, L2-normalized per row
        (so cosine similarity == dot product for every implementation)."""
        raise NotImplementedError

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]


class HashingEmbedding(EmbeddingModel):
    """
    Stateless, offline, zero-network embedding via scikit-learn's
    HashingVectorizer — no vocabulary is fit or persisted, so texts embedded
    today and texts embedded after ingesting 500 more documents land in the
    exact same vector space with no re-indexing step required. This is what
    lets bulk_upsert-style incremental document ingestion (see
    rag_service.ingest_document) work without ever needing to refit or
    version a shared model.
    """
    name = "hashing_bow_v1"

    def __init__(self, dimension: int = 512):
        self.dimension = dimension
        self._vectorizer = HashingVectorizer(
            n_features=dimension,
            alternate_sign=False,  # non-negative features -- easier to reason about for TF-style weighting
            norm="l2",
            ngram_range=(1, 2),  # unigrams + bigrams: "net income" as a unit, not just "net" and "income" separately
            stop_words="english",
            # Without this, common function words ("the", "of", "a", "is")
            # inflate similarity between ANY two English passages regardless
            # of topic — discovered directly via tests/test_rag_service.py's
            # threshold test: a large real chunk of risk-factors text scored
            # above the relevance threshold against "What is the capital of
            # France?" purely on shared stopwords, even though nothing about
            # France appeared in either. Removing them means similarity
            # reflects shared CONTENT words, which is what retrieval actually
            # needs to be judged on.
        )

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        matrix = self._vectorizer.transform(texts)
        return matrix.toarray().astype(np.float32)


class OpenAIEmbedding(EmbeddingModel):
    """
    Real client for OpenAI's /v1/embeddings endpoint (text-embedding-3-small,
    1536 dimensions). Requires OPENAI_API_KEY and network egress to
    api.openai.com — neither is available in this sandbox, so this class is
    exercised in tests/test_rag_embeddings.py via httpx.MockTransport rather
    than a live call. Wiring in a real key requires no code changes here.
    """
    name = "openai_text-embedding-3-small"
    dimension = 1536
    BASE_URL = "https://api.openai.com/v1/embeddings"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAIEmbedding requires a non-empty api_key")
        self.api_key = api_key

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        with httpx.Client() as client:
            response = client.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": "text-embedding-3-small", "input": texts},
                timeout=30.0,
            )
        response.raise_for_status()
        payload = response.json()
        # OpenAI returns results in the same order as the input list, but
        # sorts the `data` array by `index` explicitly -- don't assume
        # response order matches request order without checking.
        ordered = sorted(payload["data"], key=lambda d: d["index"])
        vectors = np.array([d["embedding"] for d in ordered], dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)
