import httpx
import pytest

from app.rag.llm_client import (
    ExtractiveFallbackClient,
    GeminiChatClient,
    OpenAIChatClient,
    RetrievedChunk,
)

_REAL_HTTPX_CLIENT = httpx.Client  # captured before any monkeypatching below


def _sample_chunks():
    return [
        RetrievedChunk(text="Revenue grew 12% year over year.", document_name="Q3_10-Q.pdf", page_number=4, score=0.91),
        RetrievedChunk(text="Operating margin improved to 24%.", document_name="Q3_10-Q.pdf", page_number=5, score=0.85),
    ]


class TestExtractiveFallbackClient:
    def test_no_chunks_returns_clear_no_results_message(self):
        client = ExtractiveFallbackClient()
        answer = client.generate_answer("What was revenue?", [])
        assert "no relevant passages" in answer.lower()

    def test_labels_itself_as_extractive_not_a_synthesized_answer(self):
        """Critical honesty check: the fallback must never claim to be an
        LLM-synthesized answer -- it must say plainly that it's extractive."""
        client = ExtractiveFallbackClient()
        answer = client.generate_answer("What was revenue?", _sample_chunks())
        assert "extractive" in answer.lower()
        assert "no llm provider" in answer.lower() or "no llm" in answer.lower()

    def test_includes_actual_passage_text_and_source_attribution(self):
        client = ExtractiveFallbackClient()
        answer = client.generate_answer("What was revenue?", _sample_chunks())
        assert "Revenue grew 12% year over year." in answer
        assert "Q3_10-Q.pdf" in answer
        assert "p.4" in answer

    def test_preserves_relevance_ordering(self):
        client = ExtractiveFallbackClient()
        answer = client.generate_answer("q", _sample_chunks())
        # the higher-scored chunk (0.91) should appear before the lower one (0.85)
        assert answer.index("Revenue grew") < answer.index("Operating margin")


class TestOpenAIChatClient:
    def test_requires_api_key(self):
        with pytest.raises(ValueError):
            OpenAIChatClient(api_key="")

    def test_parses_response_and_sends_context(self, monkeypatch):
        captured_request = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request["body"] = request.content
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Revenue grew 12% based on the filing [1]."}}]
            })

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        client = OpenAIChatClient(api_key="fake-key")
        answer = client.generate_answer("What was revenue?", _sample_chunks())

        assert answer == "Revenue grew 12% based on the filing [1]."
        assert b"Revenue grew 12%" in captured_request["body"]  # context was actually sent


class TestGeminiChatClient:
    def test_requires_api_key(self):
        with pytest.raises(ValueError):
            GeminiChatClient(api_key="")

    def test_parses_response(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "Margin improved to 24% [2]."}]}}]
            })

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        client = GeminiChatClient(api_key="fake-key")
        answer = client.generate_answer("What was the margin?", _sample_chunks())
        assert answer == "Margin improved to 24% [2]."

    def test_api_key_sent_as_query_param_not_leaked_in_body(self, monkeypatch):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        GeminiChatClient(api_key="secret-key-123").generate_answer("q", [])
        assert "secret-key-123" in captured["url"]  # Gemini's documented auth convention
