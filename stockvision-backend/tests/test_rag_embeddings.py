import numpy as np
import pytest

from app.rag.embeddings import HashingEmbedding, OpenAIEmbedding


class TestHashingEmbedding:
    def test_output_shape(self):
        model = HashingEmbedding(dimension=256)
        vectors = model.embed_batch(["hello world", "financial report"])
        assert vectors.shape == (2, 256)

    def test_empty_batch_returns_empty_array_not_error(self):
        model = HashingEmbedding(dimension=256)
        vectors = model.embed_batch([])
        assert vectors.shape == (0, 256)

    def test_deterministic_same_text_same_vector(self):
        model = HashingEmbedding()
        v1 = model.embed_one("Revenue grew 12% year over year")
        v2 = model.embed_one("Revenue grew 12% year over year")
        assert np.allclose(v1, v2)

    def test_vectors_are_l2_normalized(self):
        model = HashingEmbedding()
        vectors = model.embed_batch(["Some financial text about earnings and revenue growth"])
        norm = np.linalg.norm(vectors[0])
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_similar_text_scores_higher_than_unrelated_text(self):
        """Core sanity check for ANY embedding model used in retrieval: a
        query about revenue should be closer (higher cosine similarity) to a
        passage about revenue than to an unrelated passage about the weather."""
        model = HashingEmbedding()
        query = model.embed_one("What was the company's revenue growth?")
        relevant = model.embed_one("The company's revenue growth was twelve percent this quarter")
        unrelated = model.embed_one("The weather today is sunny with a light breeze")

        sim_relevant = float(np.dot(query, relevant))
        sim_unrelated = float(np.dot(query, unrelated))
        assert sim_relevant > sim_unrelated

    def test_different_dimensions_are_configurable(self):
        model = HashingEmbedding(dimension=128)
        vectors = model.embed_batch(["test"])
        assert vectors.shape == (1, 128)

    def test_stopwords_do_not_dominate_similarity(self):
        """
        Regression test for a real calibration finding: before stop_words
        removal was added, two passages sharing only common function words
        ("the", "of", "a") scored non-trivially similar regardless of topic.
        A query and a passage sharing ONLY stopwords should score ~0.
        """
        model = HashingEmbedding()
        query = model.embed_one("the of a is in")  # pure stopwords, should embed as ~zero vector
        content = model.embed_one("Revenue grew twelve percent this quarter")
        assert float(np.dot(query, content)) == pytest.approx(0.0, abs=1e-6)

    def test_default_dimension_separates_offtopic_noise_from_real_relevance(self):
        """
        Regression test for the dimensionality calibration in
        app/services/rag_service.py's MIN_RELEVANCE_SCORE docstring: at the
        PROJECT'S DEFAULT dimension, genuinely off-topic queries must score
        well below genuinely relevant ones, with real margin -- at the
        originally-tried 512 dimensions, hash collisions made this fail
        (an off-topic query scored HIGHER than a relevant one).
        """
        from app.core.config import settings

        model = HashingEmbedding(dimension=settings.RAG_EMBEDDING_DIMENSION)
        financial_chunk = model.embed_one(
            "Total revenue for the third quarter was 412.6 million dollars, "
            "an increase of fourteen percent compared to the prior year."
        )
        relevant_query = model.embed_one("What was total revenue this quarter?")
        offtopic_query = model.embed_one("Describe the mating rituals of Emperor penguins in Antarctica")

        relevant_score = float(np.dot(relevant_query, financial_chunk))
        offtopic_score = float(np.dot(offtopic_query, financial_chunk))

        assert relevant_score > offtopic_score
        assert relevant_score - offtopic_score > 0.1  # real, usable margin -- not just "technically higher"


class TestOpenAIEmbedding:
    def test_requires_api_key(self):
        with pytest.raises(ValueError):
            OpenAIEmbedding(api_key="")

    def test_parses_response_and_normalizes(self, monkeypatch):
        import httpx

        real_client = httpx.Client

        def fake_client(**kwargs):
            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={
                    "data": [
                        {"index": 1, "embedding": [3.0, 4.0]},  # norm 5 -> normalized to [0.6, 0.8]
                        {"index": 0, "embedding": [1.0, 0.0]},  # deliberately out of order
                    ]
                })
            return real_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(httpx, "Client", fake_client)

        model = OpenAIEmbedding(api_key="fake-key")
        vectors = model.embed_batch(["first text", "second text"])

        assert vectors.shape == (2, 2)
        # index 0 (first text) should be [1, 0] despite arriving second in the response
        assert np.allclose(vectors[0], [1.0, 0.0])
        assert np.allclose(vectors[1], [0.6, 0.8])

    def test_empty_batch_returns_empty_array(self):
        model = OpenAIEmbedding(api_key="fake-key")
        vectors = model.embed_batch([])
        assert vectors.shape == (0, 1536)
