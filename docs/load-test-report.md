# Load Test Report

**Date:** 2026-06-26
**Scope:** Smoke test only — full run requires live Docker stack
**Status:** Test script shipped, actual numbers pending infra setup

## Target SLOs (per PRD)

| Metric | Target |
|---|---|
| p50 query latency (simple RAG) | < 2s |
| p95 query latency (full pipeline) | < 8s |
| Sustained QPS | 10 req/s |
| Error rate | < 1% |

## Test script

Saved as `backend/loadtest/run_loadtest.sh`.

## How to run (when infra available)

```bash
# Start stack
cd backend
docker compose up -d

# Wait for healthy
docker compose ps
# backend should show "(healthy)"

# Run load test
./loadtest/run_loadtest.sh
```

## Methodology

- Tool: `wrk` (4 threads, 100 connections)
- Duration: 60s sustained
- Endpoints: 70% `/api/v1/chat/query` (with valid JWT), 30% `/api/v1/chat/query` (casual greeting)
- Auth: pre-generated system_admin JWT
- Cold cache: run 1 discarded (warm-up)
- Reported: run 2 + run 3 average

## Pending measurements

| Test | Setup needed | Expected |
|---|---|---|
| Baseline RAG p95 | 8GB GPU Ollama + Groq | < 8s |
| Concurrent 10 QPS | 8GB GPU Ollama | p95 < 8s, err < 1% |
| Burst 50 QPS | 8GB GPU Ollama | p95 < 12s, err < 5% |

## Known bottlenecks

1. **Embedding latency** — Ollama 4-retry exponential backoff on network errors
2. **DuckDuckGo rate limit** — web search degrades to cache hits after burst
3. **LLM cold start** — first request after idle > 5min may take +1-2s

## Optimization levers

| Lever | Effort | Expected gain |
|---|---|---|
| Connection pool size (DB) | Low | +20% throughput |
| Redis cache TTL tuning | Low | -30% LLM calls |
| Embedding batch | Med | -50% embedding latency |
| Pre-warm LLM on startup | Med | -1-2s p50 on cold start |
| Async price pipeline | Med | -1s price query p95 |
