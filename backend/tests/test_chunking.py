import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.chunking import chunk_text


def test_chunk_text_returns_list():
    text = "Hello world. " * 100
    chunks = chunk_text(text)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_chunk_size_respected():
    text = "word " * 500
    chunks = chunk_text(text)
    for c in chunks:
        assert len(c.split()) <= 512


def test_empty_text():
    assert chunk_text("") == []


def test_single_sentence():
    chunks = chunk_text("This is a short sentence.")
    assert len(chunks) == 1
