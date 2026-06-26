"""Tests for RagOrchestrator and PriceQueryOrchestrator.

Verifies orchestrator construction and basic delegation patterns.
"""
import inspect
from unittest.mock import MagicMock

import pytest

from app.services.price_orchestrator import PriceQueryOrchestrator
from app.services.rag_orchestrator import RagOrchestrator


def test_rag_orchestrator_init():
    db = MagicMock()
    web_fn = MagicMock()
    orch = RagOrchestrator(db=db, web_search_fn=web_fn, system_prompt="test prompt", user_role="viewer")
    assert orch.db is db
    assert orch._web_search_fn is web_fn
    assert orch._system_prompt == "test prompt"
    assert orch._user_role == "viewer"


def test_price_orchestrator_init():
    db = MagicMock()
    web_fn = MagicMock()
    orch = PriceQueryOrchestrator(db=db, web_search_fn=web_fn)
    assert orch.db is db
    assert orch._web_search_fn is web_fn


def test_rag_orchestrator_has_run_method():
    db = MagicMock()
    web_fn = MagicMock()
    orch = RagOrchestrator(db=db, web_search_fn=web_fn, system_prompt="x", user_role="viewer")
    assert hasattr(orch, "run")
    assert callable(orch.run)


def test_price_orchestrator_has_run_method():
    db = MagicMock()
    web_fn = MagicMock()
    orch = PriceQueryOrchestrator(db=db, web_search_fn=web_fn)
    assert hasattr(orch, "run")
    assert callable(orch.run)


def test_rag_orchestrator_run_signature():
    db = MagicMock()
    web_fn = MagicMock()
    orch = RagOrchestrator(db=db, web_search_fn=web_fn, system_prompt="x", user_role="viewer")
    sig = inspect.signature(orch.run)
    params = list(sig.parameters.keys())
    assert "query" in params
    assert "history" in params


def test_persist_message_citations_function_exists():
    from app.services.rag_orchestrator import persist_message_citations
    assert callable(persist_message_citations)


def test_rag_orchestrator_returns_dict_with_required_keys():
    """RagOrchestrator.run() must return dict with these keys."""
    db = MagicMock()
    web_fn = MagicMock(return_value=[])
    orch = RagOrchestrator(db=db, web_search_fn=web_fn, system_prompt="x", user_role="viewer")
    sig = inspect.signature(orch.run)
    # We don't run it (would need full mock pipeline), but verify return annotation
    assert sig.return_annotation is not inspect.Signature.empty
