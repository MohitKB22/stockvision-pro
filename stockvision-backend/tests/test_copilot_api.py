"""
AI Copilot (RAG) API tests.

CHANGE LOG (v2.0): the role-based upload test and the per-user history test are
gone with authentication. Conversation-threading tests are added, since a question
can now belong to a thread.
"""
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_pdfs"
TENQ_PATH = SAMPLE_DIR / "meridian_robotics_10q_q3_2025.pdf"
EARNINGS_CALL_PATH = SAMPLE_DIR / "meridian_robotics_earnings_call_q3_2025.pdf"


def _ensure_sample_pdfs():
    if not TENQ_PATH.exists() or not EARNINGS_CALL_PATH.exists():
        import subprocess
        script = Path(__file__).resolve().parent.parent / "scripts" / "generate_sample_documents.py"
        subprocess.run(["python3", str(script)], check=True)


def _upload_10q(client, stock_symbol=None):
    _ensure_sample_pdfs()
    with open(TENQ_PATH, "rb") as f:
        data = {"document_type": "quarterly_report"}
        if stock_symbol:
            data["stock_symbol"] = stock_symbol
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("meridian_10q.pdf", f, "application/pdf")},
            data=data,
        )
    return resp


class TestDocumentUpload:
    def test_upload_pdf_succeeds_and_creates_chunks(self, client):
        resp = _upload_10q(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["page_count"] == 3
        assert body["chunks_created"] > 0
        assert body["pages_with_no_extractable_text"] == []

    def test_upload_rejects_non_pdf_extension(self, client):
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", b"just some text", "text/plain")},
            data={"document_type": "quarterly_report"},
        )
        assert resp.status_code == 400

    def test_upload_rejects_invalid_document_type(self, client):
        _ensure_sample_pdfs()
        with open(TENQ_PATH, "rb") as f:
            resp = client.post(
                "/api/v1/documents/upload",
                files={"file": ("meridian_10q.pdf", f, "application/pdf")},
                data={"document_type": "not_a_real_type"},
            )
        # v2.0: document_type is a DocumentType enum on the endpoint signature, so
        # FastAPI rejects it during validation (422) before the handler runs —
        # stricter than v1's hand-rolled 400 check, and self-documenting in the
        # OpenAPI schema.
        assert resp.status_code == 422

    def test_upload_scoped_to_a_stock_requires_stock_to_exist(self, client):
        _ensure_sample_pdfs()
        with open(TENQ_PATH, "rb") as f:
            resp = client.post(
                "/api/v1/documents/upload",
                files={"file": ("meridian_10q.pdf", f, "application/pdf")},
                data={"document_type": "quarterly_report", "stock_symbol": "NOSUCHTICKER"},
            )
        assert resp.status_code == 404

    def test_list_documents_after_upload(self, client):
        _upload_10q(client)
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestCopilotQuery:
    def test_query_with_no_documents_returns_422(self, client):
        resp = client.post(
            "/api/v1/copilot/query", json={"question": "What was revenue?"}
        )
        assert resp.status_code == 422

    def test_query_retrieves_relevant_passage_and_cites_it(self, client):
        _upload_10q(client)
        resp = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was the total revenue this quarter?", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_provider"] == "extractive_fallback"  # no API key configured in this sandbox
        assert len(body["citations"]) > 0
        # The actual revenue figure from the source PDF should appear in at
        # least one citation -- proves retrieval found the RIGHT passage,
        # not just *a* passage.
        assert any("412.6 million" in c["chunk_text"] for c in body["citations"])
        assert all(c["document_name"] == "meridian_10q.pdf" for c in body["citations"])

    def test_query_answer_is_labeled_as_extractive(self, client):
        """Honesty check at the API level, not just the unit level."""
        _upload_10q(client)
        resp = client.post(
            "/api/v1/copilot/query", json={"question": "What was the gross margin?"}
        )
        assert "extractive" in resp.json()["answer"].lower()

    def test_query_scoped_to_stock_only_searches_that_stocks_documents(self, client):
        client.post(
            "/api/v1/stocks", json={"symbol": "MRDN", "name": "Meridian Robotics", "exchange": "NASDAQ"},
        )
        _upload_10q(client, stock_symbol="MRDN")

        # Querying scoped to a DIFFERENT (also-real) stock with no documents should 422
        client.post(
            "/api/v1/stocks", json={"symbol": "OTHR", "name": "Other Corp", "exchange": "NYSE"},
        )
        resp = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was revenue?", "stock_symbol": "OTHR"},
        )
        assert resp.status_code == 422

        # But querying scoped to MRDN (which has the document) should work
        resp2 = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was revenue?", "stock_symbol": "MRDN"},
        )
        assert resp2.status_code == 200

    def test_query_unknown_stock_symbol_returns_404(self, client):
        _upload_10q(client)
        resp = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was revenue?", "stock_symbol": "NOSUCHTICKER"},
        )
        assert resp.status_code == 404

    def test_query_history_is_persisted_and_retrievable(self, client):
        _upload_10q(client)
        client.post(
            "/api/v1/copilot/query", json={"question": "What was the risk factor about suppliers?"},
        )
        history_resp = client.get("/api/v1/copilot/history")
        assert history_resp.status_code == 200
        assert len(history_resp.json()) >= 1
        assert history_resp.json()[0]["question"] == "What was the risk factor about suppliers?"

    def test_chromadb_backend_produces_equivalent_results_to_faiss(self, client):
        _upload_10q(client)
        faiss_resp = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was total revenue?", "vector_store_backend": "faiss", "top_k": 1},
        )
        chroma_resp = client.post(
            "/api/v1/copilot/query",
            json={"question": "What was total revenue?", "vector_store_backend": "chromadb", "top_k": 1},
        )
        assert faiss_resp.status_code == 200
        assert chroma_resp.status_code == 200
        # Both backends should retrieve the SAME top passage for the same query
        assert faiss_resp.json()["citations"][0]["chunk_text"] == chroma_resp.json()["citations"][0]["chunk_text"]


class TestConversations:
    def test_questions_can_be_threaded_into_a_conversation(self, client):
        _upload_10q(client)
        conversation = client.post(
            "/api/v1/copilot/conversations", json={"title": "New conversation"}
        ).json()

        client.post("/api/v1/copilot/query", json={
            "question": "What was total revenue?", "conversation_id": conversation["id"],
        })
        detail = client.get(f"/api/v1/copilot/conversations/{conversation['id']}").json()
        assert len(detail["messages"]) == 1
        # The first question becomes the thread title, so the history sidebar is
        # readable instead of a list of "New conversation".
        assert detail["title"] == "What was total revenue?"
        assert detail["message_count"] == 1

    def test_deleting_a_conversation_cascades_to_its_messages(self, client):
        _upload_10q(client)
        conversation = client.post("/api/v1/copilot/conversations", json={"title": "Temp"}).json()
        client.post("/api/v1/copilot/query", json={
            "question": "What was revenue?", "conversation_id": conversation["id"],
        })
        assert client.delete(f"/api/v1/copilot/conversations/{conversation['id']}").status_code == 200
        assert client.get(f"/api/v1/copilot/conversations/{conversation['id']}").status_code == 404

    def test_answers_report_their_latency(self, client):
        _upload_10q(client)
        body = client.post("/api/v1/copilot/query", json={"question": "What was revenue?"}).json()
        assert body["latency_ms"] is not None and body["latency_ms"] >= 0

    def test_empty_upload_is_rejected(self, client):
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            data={"document_type": "quarterly_report"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "empty_file"

    def test_deleting_a_document_removes_it_from_retrieval(self, client):
        upload = _upload_10q(client)
        document_id = upload.json()["id"]
        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 200
        # With the corpus empty again, a query has nothing to retrieve from.
        response = client.post("/api/v1/copilot/query", json={"question": "What was revenue?"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "insufficient_data"

    def test_suggested_prompts_are_served(self, client):
        prompts = client.get("/api/v1/copilot/prompts").json()
        assert prompts and {"label", "prompt", "category"} <= set(prompts[0])
