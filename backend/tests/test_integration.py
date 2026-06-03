"""
Integration tests for the RAG pipeline.
Requires Qdrant, PostgreSQL, and API keys to be running.
Skipped by default - run with: pytest --run-integration
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_imports():
    """Verify all core modules can be imported."""
    from app.services.embedding import generate_embedding
    from app.services.chunking import chunk_text
    from app.services.groq_client import get_groq
    from app.services.qdrant_client import get_qdrant
    assert generate_embedding is not None
    assert chunk_text is not None
    assert get_groq is not None
    assert get_qdrant is not None
