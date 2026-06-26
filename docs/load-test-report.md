# Load Test Report

**Date:** 2026-06-26
**Status:** Test script shipped, full run requires live Docker stack
**Tool:** `wrk` (4 threads, 100 connections, 60s sustained)

## Target SLOs (per PRD)

| Metric | Target |
|---|---|
| p50 query latency (simple RAG) | < 2s |
| p95 query latency (full pipeline) | < 8s |
| Sustained QPS | 10 req/s |
| Error rate | < 1% |

## Test script

Saved as `backend/loadtest/run_loadtest.sh`.

## How to run

```bash
# Start stack
cd backend
docker compose up -d

# Wait for backend healthy
docker compose ps
# backend should show "(healthy)"

# Get JWT token
export JWT_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r .token)

# Run load test
./loadtest/run_loadtest.sh http://localhost:8000 60 4 100
```

## Workload mix

70% RAG queries (`{"query":"apa itu SOP cuti?","session_id":null}`), 30% casual greetings (`{"query":"halo","session_id":null}`).

Auth: pre-generated system_admin JWT via `Authorization: Bearer` header.

## Methodology

- Tool: `wrk` (Lua script for mixed workload)
- Duration: 60s sustained
- Cold cache: run 1 discarded (warm-up)
- Reported: run 2 + run 3 average

## Pending measurements (need live infra)

| Test | Setup needed | Expected |
|---|---|---|
| Baseline RAG p95 | 8GB GPU Ollama + Groq | < 8s |
| Concurrent 10 QPS | 8GB GPU Ollama | p95 < 8s, err < 1% |
| Burst 50 QPS | 8GB GPU Ollama | p95 < 12s, err < 5% |

## Known bottlenecks

1. **Embedding latency** — Ollama 4-retry exponential backoff on network errors
2. **DuckDuckGo rate limit** — web search degrades to cache hits after burst
3. **LLM cold start** — first request after idle > 5min may take +1-2s
4. **Qdrant cold start** — first search after container start loads indexes

## Optimization levers

| Lever | Effort | Expected gain |
|---|---|---|
| Connection pool size (DB) | Low | +20% throughput |
| Redis cache TTL tuning | Low | -30% LLM calls |
| Embedding batch | Med | -50% embedding latency |
| Pre-warm LLM on startup | Med | -1-2s p50 on cold start |
| Async price pipeline | Med | -1s price query p95 |
| Web search circuit breaker | Low | prevent hang on DDG outage |

## SLO monitoring

Prometheus alerts (see `docs/deployment.md`):

```yaml
- alert: ChatHighP95
  expr: histogram_quantile(0.95, http_request_duration_seconds_bucket{path="/api/v1/chat/query"}) > 8
  for: 5m
- alert: ChatHighErrorRate
  expr: rate(http_requests_total{path="/api/v1/chat/query",status=~"5.."}[5m]) > 0.01
  for: 5m
- alert: ChatAbstainSpike
  expr: rate(answerability_abstains_total[5m]) > 1
  for: 10m
```
