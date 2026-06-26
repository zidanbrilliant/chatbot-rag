"""Prometheus metrics — request-level + business-level counters.

Ponytail: separate registry per app. Skip default registry to avoid
double-registration in tests.
"""
from __future__ import annotations

import time

from fastapi import Request
from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.responses import Response

REGISTRY = CollectorRegistry()

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0),
    registry=REGISTRY,
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)

CHAT_QUERIES = Counter(
    "chat_queries_total",
    "Chat queries by intent and outcome",
    ["intent", "outcome"],
    registry=REGISTRY,
)

INGESTION_JOBS = Counter(
    "ingestion_jobs_total",
    "Document ingestion jobs by outcome",
    ["status"],
    registry=REGISTRY,
)

CITATION_VALIDATION = Counter(
    "citation_validations_total",
    "Citation validation results",
    ["result"],  # valid | invalid | regenerated
    registry=REGISTRY,
)

ABSTAIN_COUNT = Counter(
    "answerability_abstains_total",
    "Cases where answerability gate refused to answer",
    ["reason"],
    registry=REGISTRY,
)


def record_chat_intent(intent: str, outcome: str) -> None:
    CHAT_QUERIES.labels(intent=intent, outcome=outcome).inc()


def record_ingestion(status: str) -> None:
    INGESTION_JOBS.labels(status=status).inc()


def record_citation(result: str) -> None:
    CITATION_VALIDATION.labels(result=result).inc()


def record_abstain(reason: str) -> None:
    ABSTAIN_COUNT.labels(reason=reason).inc()


async def metrics_middleware(request: Request, call_next):
    """Record request latency + count for every endpoint."""
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start

    # Use route template if available, fallback to raw path
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path) if route else request.url.path

    status = str(response.status_code)
    REQUEST_COUNT.labels(method=request.method, path=path, status=status).inc()
    REQUEST_LATENCY.labels(method=request.method, path=path, status=status).observe(elapsed)
    return response


def render_metrics() -> Response:
    """Render metrics in Prometheus text format."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
