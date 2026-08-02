"""
LLM answer-generation clients for the RAG Financial Copilot.

Design decision — the fallback is honest about what it is: this sandbox has
no OPENAI_API_KEY/GEMINI_API_KEY configured and no network egress to either
provider (see network_configuration — api.openai.com and
generativelanguage.googleapis.com are not in the allowed domains list), so
ExtractiveFallbackClient is what actually answers queries here and in any
deployment that hasn't configured a real LLM key yet. It does NOT claim to
summarize or synthesize anything — it returns the retrieved passages
themselves, ranked and labeled, because a fabricated-sounding "answer" from
string concatenation would misrepresent what actually happened. OpenAIChatClient
and GeminiChatClient are real, complete client implementations for when a key
and network access are available; they're exercised in
tests/test_rag_llm_client.py via httpx.MockTransport.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass
class RetrievedChunk:
    text: str
    document_name: str
    page_number: int
    score: float


class LLMClient(ABC):
    name: str

    @abstractmethod
    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        raise NotImplementedError


class ExtractiveFallbackClient(LLMClient):
    """
    No external call, no synthesis — returns the top retrieved passages
    verbatim, each labeled with its source document and page, in relevance
    order. This is what runs whenever no LLM provider is configured (the
    default in this project — see get_llm_client() in
    app/services/rag_service.py) and is a legitimate degraded mode, not a
    stand-in pretending to be something it isn't.
    """
    name = "extractive_fallback"

    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return (
                "No relevant passages were found in the uploaded documents for this question. "
                "(Extractive mode: no LLM provider is configured, so this system can only surface "
                "retrieved passages, not synthesize an answer beyond what was retrieved.)"
            )
        lines = [
            "Extractive mode (no LLM provider configured): showing the most relevant "
            "retrieved passages rather than a synthesized answer.",
            "",
        ]
        for i, chunk in enumerate(chunks, start=1):
            lines.append(f"[{i}] {chunk.document_name}, p.{chunk.page_number} (relevance {chunk.score:.2f}):")
            lines.append(f"    {chunk.text}")
            lines.append("")
        return "\n".join(lines).strip()


class OpenAIChatClient(LLMClient):
    """Real client for OpenAI's /v1/chat/completions. Requires OPENAI_API_KEY
    + network egress to api.openai.com, neither available in this sandbox."""
    name = "openai_gpt-4o-mini"
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OpenAIChatClient requires a non-empty api_key")
        self.api_key = api_key
        self.model = model

    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        context = _format_context_for_prompt(chunks)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ]
        with httpx.Client() as client:
            response = client.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.2},
                timeout=60.0,
            )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


class GeminiChatClient(LLMClient):
    """Real client for Gemini's generateContent endpoint. Requires
    GEMINI_API_KEY + network egress to generativelanguage.googleapis.com,
    neither available in this sandbox."""
    name = "gemini-1.5-flash"
    BASE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        if not api_key:
            raise ValueError("GeminiChatClient requires a non-empty api_key")
        self.api_key = api_key
        self.model = model

    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        context = _format_context_for_prompt(chunks)
        prompt = f"{_SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {question}"
        url = self.BASE_URL_TEMPLATE.format(model=self.model)

        with httpx.Client() as client:
            response = client.post(
                url,
                params={"key": self.api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60.0,
            )
        response.raise_for_status()
        payload = response.json()
        return payload["candidates"][0]["content"]["parts"][0]["text"]


_SYSTEM_PROMPT = (
    "You are a financial research assistant. Answer the question using ONLY the "
    "provided context from the company's filings. If the context does not contain "
    "the answer, say so explicitly rather than guessing. Cite passage numbers like [1] "
    "when you use a specific fact."
)


def _format_context_for_prompt(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{i}] ({chunk.document_name}, p.{chunk.page_number}): {chunk.text}"
        for i, chunk in enumerate(chunks, start=1)
    )
