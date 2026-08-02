from app.rag.chunking import chunk_document, chunk_page_text


class TestChunkPageText:
    def test_short_text_is_a_single_chunk(self):
        text = "This is a short sentence. Here is another one."
        chunks = chunk_page_text(text, target_chars=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_is_split_into_multiple_chunks(self):
        sentence = "This is a moderately long sentence about company revenue. "
        text = sentence * 50  # ~3000 chars
        chunks = chunk_page_text(text, target_chars=500, overlap_chars=50)
        assert len(chunks) > 1
        for c in chunks:
            # Allow some slack: a chunk may slightly exceed target_chars if a
            # single sentence is long, but shouldn't blow past it wildly.
            assert len(c) < 1000

    def test_no_sentence_is_split_mid_word(self):
        text = "Revenue grew twelve percent year over year. Costs declined slightly. Margins expanded."
        chunks = chunk_page_text(text, target_chars=40, overlap_chars=10)
        rejoined_words = set(" ".join(chunks).replace(".", "").split())
        original_words = set(text.replace(".", "").split())
        # Every original word must appear whole somewhere in the chunked output
        assert original_words.issubset(rejoined_words)

    def test_consecutive_chunks_share_overlap_content(self):
        sentences = [f"Fact number {i} about the business." for i in range(20)]
        text = " ".join(sentences)
        chunks = chunk_page_text(text, target_chars=150, overlap_chars=60)
        assert len(chunks) >= 2
        # The tail of chunk N should share at least one sentence with the head of chunk N+1.
        # Strip trailing periods before comparing: naively splitting on ". " leaves
        # the period attached to whichever piece happens to be LAST in a chunk
        # (nothing follows it to consume it as a separator) but stripped from
        # every other piece -- a string-formatting artifact of the test's own
        # comparison, not a signal about the chunker's actual behavior.
        for i in range(len(chunks) - 1):
            tail_sentences = {s.rstrip(".") for s in chunks[i].split(". ")}
            head_sentences = {s.rstrip(".") for s in chunks[i + 1].split(". ")}
            assert tail_sentences & head_sentences, f"No overlap between chunk {i} and {i+1}"

    def test_empty_text_returns_no_chunks(self):
        assert chunk_page_text("") == []
        assert chunk_page_text("   ") == []

    def test_single_very_long_sentence_is_not_split(self):
        """We never cut mid-sentence, even if a sentence exceeds target_chars."""
        long_sentence = "Revenue " + "grew " * 200 + "significantly."
        chunks = chunk_page_text(long_sentence, target_chars=100, overlap_chars=20)
        assert len(chunks) == 1
        assert chunks[0] == long_sentence


class TestChunkDocument:
    def test_chunks_retain_correct_page_numbers(self):
        pages = [
            (1, "Page one content here. More page one content."),
            (2, "Page two content here. More page two content."),
        ]
        chunks = chunk_document(pages, target_chars=1000)
        assert chunks[0].page_number == 1
        assert chunks[1].page_number == 2

    def test_chunk_index_is_globally_sequential_across_pages(self):
        pages = [(1, "Sentence one. Sentence two."), (2, "Sentence three. Sentence four.")]
        chunks = chunk_document(pages, target_chars=15, overlap_chars=0)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_pages_produce_no_chunks_but_dont_crash(self):
        pages = [(1, ""), (2, "Real content on page two.")]
        chunks = chunk_document(pages)
        assert all(c.page_number == 2 for c in chunks)
