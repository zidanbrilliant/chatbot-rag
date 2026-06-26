"""Tests for evaluation runner."""
from pathlib import Path

import pytest


def test_runner_module_imports():
    from evals import runner
    assert hasattr(runner, "main")
    assert hasattr(runner, "load_cases")
    assert hasattr(runner, "run_case")


def test_load_cases_reads_yaml():
    from evals.runner import load_cases
    cases_path = Path("evals/cases.yaml")
    if not cases_path.exists():
        pytest.skip("cases.yaml not present")
    cases = load_cases(cases_path)
    assert isinstance(cases, list)
    assert len(cases) >= 20
    for c in cases:
        assert "id" in c
        assert "query" in c
        assert "intent" in c


def test_run_case_passes_for_known_intent():
    from evals.runner import run_case
    result = run_case({"id": "test1", "query": "halo", "intent": "casual_greeting"})
    assert result["passed"] is True
    assert result["actual_intent"] == "casual_greeting"


def test_run_case_fails_for_mismatch():
    from evals.runner import run_case
    result = run_case({"id": "test1", "query": "halo", "intent": "rag_question"})
    assert result["passed"] is False
    assert "intent mismatch" in result["reasons"][0]


def test_run_case_checks_refuse_message():
    from evals.runner import run_case
    case = {
        "id": "oos1",
        "query": "buatkan pantun",
        "intent": "out_of_scope",
        "expect_refuse": True,
        "expect_keywords": ["maaf"],
    }
    result = run_case(case)
    assert result["passed"] is True


def test_run_case_fails_missing_keyword():
    from evals.runner import run_case
    case = {
        "id": "oos2",
        "query": "buatkan pantun",
        "intent": "out_of_scope",
        "expect_refuse": True,
        "expect_keywords": ["NONEXISTENT_KEYWORD"],
    }
    result = run_case(case)
    assert result["passed"] is False
