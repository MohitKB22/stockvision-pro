import numpy as np
import pytest

from app.rag.vector_store import ChromaDBVectorStore, FAISSVectorStore, new_vector_store


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


# Three L2-normalized vectors with known, hand-computable relationships:
# v_a and v_b are close (small angle); v_c is far (orthogonal-ish).
V_A = _normalize(np.array([1.0, 0.1, 0.0]))
V_B = _normalize(np.array([1.0, 0.2, 0.0]))  # close to V_A
V_C = _normalize(np.array([0.0, 0.0, 1.0]))  # orthogonal to both


@pytest.fixture(params=["faiss", "chromadb"])
def store(request):
    return new_vector_store(request.param)


class TestVectorStoreCommonBehavior:
    """Every VectorStore implementation must satisfy these -- run against both backends."""

    def test_empty_store_returns_no_results(self, store):
        store.build(ids=[], vectors=np.zeros((0, 3)), metadatas=[])
        results = store.search(V_A, top_k=5)
        assert results == []

    def test_exact_match_scores_highest_and_returns_correct_id(self, store):
        vectors = np.stack([V_A, V_B, V_C])
        store.build(ids=["a", "b", "c"], vectors=vectors, metadatas=[{"label": "a"}, {"label": "b"}, {"label": "c"}])

        results = store.search(V_A, top_k=3)
        assert results[0].id == "a"
        assert results[0].score == pytest.approx(1.0, abs=1e-4)

    def test_ranking_prefers_similar_vector_over_orthogonal_one(self, store):
        vectors = np.stack([V_A, V_B, V_C])
        store.build(ids=["a", "b", "c"], vectors=vectors, metadatas=[{}, {}, {}])

        results = store.search(V_A, top_k=3)
        ranked_ids = [r.id for r in results]
        assert ranked_ids.index("b") < ranked_ids.index("c")  # b (close) ranked above c (orthogonal)

    def test_top_k_limits_result_count(self, store):
        vectors = np.stack([V_A, V_B, V_C])
        store.build(ids=["a", "b", "c"], vectors=vectors, metadatas=[{}, {}, {}])
        results = store.search(V_A, top_k=2)
        assert len(results) == 2

    def test_top_k_larger_than_index_size_does_not_crash(self, store):
        vectors = np.stack([V_A, V_B])
        store.build(ids=["a", "b"], vectors=vectors, metadatas=[{}, {}])
        results = store.search(V_A, top_k=50)
        assert len(results) == 2

    def test_metadata_is_preserved_and_returned(self, store):
        vectors = np.stack([V_A])
        store.build(ids=["a"], vectors=vectors, metadatas=[{"document": "10-K.pdf", "page": 4}])
        results = store.search(V_A, top_k=1)
        assert results[0].metadata == {"document": "10-K.pdf", "page": 4}

    def test_rebuild_replaces_previous_contents(self, store):
        store.build(ids=["a"], vectors=np.stack([V_A]), metadatas=[{}])
        store.build(ids=["c"], vectors=np.stack([V_C]), metadatas=[{}])  # should REPLACE, not merge
        results = store.search(V_A, top_k=5)
        returned_ids = {r.id for r in results}
        assert returned_ids == {"c"}


class TestFAISSVectorStoreSpecific:
    def test_uses_inner_product_index(self):
        store = FAISSVectorStore()
        store.build(ids=["a"], vectors=np.stack([V_A]), metadatas=[{}])
        import faiss
        assert isinstance(store._index, faiss.IndexFlatIP)


class TestChromaDBDistanceConversion:
    def test_l2_to_cosine_conversion_matches_direct_dot_product(self):
        """
        Verifies the `similarity = 1 - (l2_distance / 2)` conversion used for
        Chroma's results is mathematically correct for L2-normalized vectors:
        for unit vectors, ||u - v||^2 = 2 - 2*(u . v), so 1 - (||u-v||^2 / 2)
        == u . v exactly. Checked against a real Chroma query, not just
        algebra on paper.
        """
        store = ChromaDBVectorStore()
        store.build(ids=["a", "b"], vectors=np.stack([V_A, V_B]), metadatas=[{}, {}])
        results = store.search(V_A, top_k=2)

        expected_self_similarity = float(np.dot(V_A, V_A))  # == 1.0
        expected_cross_similarity = float(np.dot(V_A, V_B))

        by_id = {r.id: r.score for r in results}
        assert by_id["a"] == pytest.approx(expected_self_similarity, abs=1e-4)
        assert by_id["b"] == pytest.approx(expected_cross_similarity, abs=1e-4)
