import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.chunking import chunk_document


def test_chunk_document_returns_list():
    docs = [{"text": "Hello world. " * 100, "page_number": 1}]
    chunks = chunk_document(docs)
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert chunks[0]["page_number"] == 1


def test_chunk_size_respected():
    docs = [{"text": "word " * 500, "page_number": 2}]
    chunks = chunk_document(docs)
    for c in chunks:
        assert len(c["text"].split()) <= 512
        assert c["page_number"] == 2


def test_empty_text():
    assert chunk_document([{"text": "", "page_number": 1}]) == []


def test_single_sentence():
    chunks = chunk_document([{"text": "This is a short sentence.", "page_number": None}])
    assert len(chunks) == 1
    assert chunks[0]["text"] == "This is a short sentence."
