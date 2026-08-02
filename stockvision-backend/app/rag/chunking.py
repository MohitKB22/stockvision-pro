"""
Text chunking for the RAG pipeline.

Design decision: chunking operates on (page_number, page_text) pairs, not a
single flattened document string — every chunk retains which page it came
from, which is what lets the copilot cite "page 14" instead of just "this
document" (see CHUNK.page_number below, threaded all the way to
CopilotQueryResponse.citations in the API layer).

Chunks try to break on paragraph/sentence boundaries within a target size
window rather than cutting at a hard character count — mid-sentence cuts
produce chunks that read as garbled fragments and hurt both embedding
quality and citation readability.
"""
import re
from dataclasses import dataclass

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int  # index within the whole document, across all pages


def _split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s.strip()]


def chunk_page_text(
    text: str, target_chars: int = 1000, overlap_chars: int = 150
) -> list[str]:
    """
    Greedily packs sentences into chunks up to ~target_chars, then starts the
    next chunk `overlap_chars` back from the end of the previous one (measured
    in whole sentences, not a mid-sentence character slice) — overlap exists
    so a fact split across a chunk boundary is still fully present in at
    least one chunk.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        if current and current_len + len(sentence) + 1 > target_chars:
            chunks.append(" ".join(current))
            # Back up into the current chunk's tail (by character budget,
            # counted in whole sentences) to build the overlap for the next one.
            overlap_sentences: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) > overlap_chars:
                    break
                overlap_sentences.insert(0, s)
                overlap_len += len(s) + 1
            current = overlap_sentences
            current_len = overlap_len
            continue  # re-attempt adding `sentence` to the now-reset `current`
        current.append(sentence)
        current_len += len(sentence) + 1
        i += 1

    if current:
        chunks.append(" ".join(current))

    # A single sentence longer than target_chars would otherwise become its
    # own (oversized) chunk above, which is correct — we never split inside a
    # sentence — but guard against a degenerate empty result on garbage input.
    return chunks if chunks else [text.strip()]


def chunk_document(pages: list[tuple[int, str]], target_chars: int = 1000, overlap_chars: int = 150) -> list[Chunk]:
    """
    pages: list of (page_number, page_text), 1-indexed page numbers, as
    returned by app.rag.pdf_extraction.extract_text_by_page.
    """
    chunks: list[Chunk] = []
    running_index = 0
    for page_number, page_text in pages:
        for piece in chunk_page_text(page_text, target_chars=target_chars, overlap_chars=overlap_chars):
            chunks.append(Chunk(text=piece, page_number=page_number, chunk_index=running_index))
            running_index += 1
    return chunks
