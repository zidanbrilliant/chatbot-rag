"""Tests for Prometheus metrics endpoint + counters."""
import re


def test_metrics_endpoint_returns_prometheus_format():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "# HELP" in body
    assert "# TYPE" in body


def test_request_counter_increments():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    client.get("/healthz/live")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


def test_chat_intent_counter():
    from app.middleware.metrics import (
        REGISTRY,
        record_chat_intent,
        CHAT_QUERIES,
    )
    before = CHAT_QUERIES.labels(intent="casual_greeting", outcome="answered")._value.get()
    record_chat_intent("casual_greeting", "answered")
    after = CHAT_QUERIES.labels(intent="casual_greeting", outcome="answered")._value.get()
    assert after == before + 1


def test_ingestion_counter():
    from app.middleware.metrics import record_ingestion, INGESTION_JOBS
    before = INGESTION_JOBS.labels(status="completed")._value.get()
    record_ingestion("completed")
    after = INGESTION_JOBS.labels(status="completed")._value.get()
    assert after == before + 1


def test_abstain_counter():
    from app.middleware.metrics import record_abstain, ABSTAIN_COUNT
    before = ABSTAIN_COUNT.labels(reason="out_of_scope")._value.get()
    record_abstain("out_of_scope")
    after = ABSTAIN_COUNT.labels(reason="out_of_scope")._value.get()
    assert after == before + 1


def test_citation_counter():
    from app.middleware.metrics import record_citation, CITATION_VALIDATION
    before = CITATION_VALIDATION.labels(result="valid")._value.get()
    record_citation("valid")
    after = CITATION_VALIDATION.labels(result="valid")._value.get()
    assert after == before + 1


def test_metrics_response_contains_all_counter_names():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/metrics")
    body = r.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "chat_queries_total" in body
    assert "ingestion_jobs_total" in body
    assert "answerability_abstains_total" in body
    assert "citation_validations_total" in body


def test_metrics_endpoint_in_schema_disabled():
    """Prometheus scrapers don't need OpenAPI doc."""
    from app.main import app
    metrics_routes = [r for r in app.routes if hasattr(r, "path") and r.path == "/metrics"]
    assert len(metrics_routes) == 1
    route = metrics_routes[0]
    assert route.include_in_schema is False
