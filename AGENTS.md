# Internal Notes — Chatbot RAG

Quick reference for developers working on this codebase. **Not for public distribution** (excluded from git by `.gitignore`).

---

## Architecture (mental model)

```
User query
  ↓
[FastAPI: auth + sanitize + injection scan]   ← middleware/auth.py
  ↓
[classify_intent()]                            ← services/general_intent.py (P1.2)
  ├─ casual_greeting  → fixed response (strict_mode.py)
  ├─ out_of_scope     → refuse (general_intent.OUT_OF_SCOPE_MESSAGE)
  ├─ price_query      → PriceQueryOrchestrator (4-way parallel: DB + file + web + marketplace)
  └─ rag_question     → RagOrchestrator (rewrite → embed → search → gate → LLM)
```

**RagOrchestrator rules (critical, PRD-aligned):**
- Web search is **supplement only** — if no internal chunks, returns `ABSTAIN_MESSAGE` with `sources=[]`
- Empty KB ≠ use web as fallback
- Answerability gate must pass on internal chunks before LLM runs

**Ponytail: where the lazy wins came from**
- `langchain-text-splitters` → inline 100 LOC splitter (H1)
- `requests` → `urllib.request` (H2)
- `chat.py` 753 → 252 LOC (extracted orchestrators, P1.3)
- Dead env vars, empty `__init__.py`, unused schemas deleted

---

## Service Architecture (backend)

```
app/
  main.py                          # FastAPI, CORS, rate-limit, prometheus, /metrics, exception handler
  config.py                        # re-export from core.config
  core/config.py                   # Pydantic Settings (env-driven)
  database.py                      # SQLAlchemy session

  middleware/
    auth.py                        # get_current_user (Bearer JWT), require_role(*roles) factory
    metrics.py                     # REQUEST_LATENCY/COUNT, CHAT_QUERIES, INGESTION_JOBS, etc.

  models/                          # no __init__.py (namespace package)
    document.py                    # Document + DocumentStatus + AccessLevel + DocumentChunk
    user.py                        # User + UserRole enum (viewer|document_admin|system_admin|auditor)
    price.py                       # Product, ProductPrice, PriceOHLC
    chat.py                        # ChatSession, ChatMessage, MessageCitation
    ingestion.py                   # IngestionJob, IngestionJobStatus
    market_price.py                # MarketPriceSnapshot
    audit.py                       # AuditLog

  routers/
    auth.py                        # /auth/login, /auth/register (system_admin only)
    chat.py                        # /chat/query (thin), /chat/feedback
    documents.py                   # /documents/upload, /documents, /documents/{id}

  schemas/                         # Pydantic request/response

  services/
    auth.py                        # hash_password (sha256+salt), verify, JWT encode/decode
    seed_admin.py                  # env-driven admin seed (ADMIN_USERNAME/PASSWORD)
    general_intent.py              # 4-intent classifier (pattern-based, adversarial-aware)
    rag_orchestrator.py            # RAG pipeline: rewrite→embed→parallel→gate→context→LLM→validate
    price_orchestrator.py          # Price pipeline: 4-way parallel + smart selection + NL formatter
    prompt_guard.py                # 5-layer prompt injection (4 categories)
    sanitizer.py                   # PII redaction (NIK/phone/email/NPWP/bank)
    answerability.py                # gate: high/medium/low/abstain
    qdrant_client.py               # search, ensure_collection, access_level filter
    embedding.py                   # bge-m3 via Ollama (lru_cache + ThreadPool)
    groq_client.py                 # dispatcher: if LLM_PROVIDER=ollama → ollama_client else groq
    ollama_client.py               # Ollama chat (urllib.request, retry 3x)
    search_client.py               # DDG + DNS patch (extra_hosts + _patch_ddg_dns)
    strict_mode.py                 # casual responses
    structured_extractor.py        # CSV/Excel date-fact extraction
    chunking.py                    # recursive text splitter (no langchain)
    price_service.py               # PG queries: catalog, OHLC, range, multi-criteria
    marketplace_scraper.py         # DDG site: per marketplace (Tokopedia/Shopee/etc)
    csv_product_mapper.py          # auto-ingest barang.csv
    scheduler.py                   # background session cleanup
    audit_log.py                   # web_search audit

  scripts/                         # ops scripts (sys.path stub)
  worker.py                        # standalone ingestion worker (polls 5s)

  alembic/versions/0001..0006       # schema migrations
  evals/                            # eval harness (cases.yaml + runner.py)
  loadtest/run_loadtest.sh          # wrk-based load test script
  tests/                            # 347 unit tests
```

---

## Critical Gotchas

| Gotcha | Why | Fix |
|--------|-----|-----|
| `alembic_version` mismatch with actual schema | Migration partial-committed but rolled back | Drop orphaned table manually (see `backfill_access_level.py`) |
| `get_cached_results` returns dicts (not `SearchResult`) | Cached JSON → list of dicts | `_search_web_with_cache` must return dicts, not raw `SearchResult` |
| `app.config` re-exports everything from `core.config` | Touching `core.config` constants needs `config.py` updated | Don't remove `app/config.py` |
| LLM_PROVIDER=ollama needs `OLLAMA_CHAT_MODEL` set | Was `OLLAMA_LLM_MODEL` (renamed in 87b6330) | Use new name |
| Backend needs `OLLAMA_BASE_URL` reachable from container | Container → host via `host.docker.internal:11434` | Works on Docker Desktop, not Linux without extra_hosts |
| Redis required for rate-limit | Backend starts without Redis (warns) | Use `host.docker.internal` or docker network |
| Qdrant points pre-P0 lack `access_level` | Filter excludes all → 0 hits | Run `backfill_access_level.py` once |
| PyJWT not in requirements.txt | P0 added JWT but forgot dep | Added in fix commit 44d7d04 |

---

## LLM Provider Switch

`LLM_PROVIDER=groq` (default) → Groq cloud via `groq_client.py:_generate_response_groq`
`LLM_PROVIDER=ollama` → local Ollama via `ollama_client.py:generate_response_ollama`

Dispatcher: `groq_client.py:generate_response()` — single call site.

Both paths share: 3x retry exp backoff, PII redaction on context, `MAX_RETRIES = 3`.

**Don't use** `qwen3.5:4b` as chat model — it's a thinking model (~29s per greeting).
**Decommissioned** Groq models: `qwen-2.5-32b`. Use `llama-3.1-8b-instant` or `llama-3.3-70b-versatile`.

---

## DuckDuckGo DNS Issue

Some Indonesian ISPs spoof DNS for `duckduckgo.com` → IP `202.169.44.80` (blocked).

Fixes (both applied):
1. `extra_hosts` in `docker-compose.yml` → maps to Cloudflare IPs
2. `_patch_ddg_dns()` in `search_client.py` — Python-level DNS override

Verify with: `nslookup duckduckgo.com 8.8.8.8`

---

## Migration History

| # | When | What |
|---|------|------|
| 0001 | initial | documents, document_chunks, ingestion_jobs, chat_*, message_citations, feedback, audit_logs, rag_evaluation_* |
| 0002 | price phase | products, product_prices |
| 0003 | OHLC | price_ohlc |
| 0004 | CSV auto-ingest | documents.attributes JSONB |
| 0005 | marketplace | market_price_snapshots |
| 0006 | auth (P0) | users + role enum |

---

## Access Level Model

Qdrant payload has `access_level: internal|restricted|confidential`. Filter on retrieval.

| Role | Role Level | Max Access | Endpoints |
|------|-----------|------------|-----------|
| viewer | 0 | internal | chat, feedback |
| document_admin | 1 | + restricted | + docs CRUD |
| system_admin | 2 | + confidential | + user mgmt |
| auditor | 3 | all (RO) | docs list |

See `qdrant_client.py:_user_max_access_level()` + `_build_filter()`.

---

## Eval Harness

`evals/cases.yaml` — 28 cases, 4 intent categories + adversarial.
`evals/runner.py` — runs against `classify_intent()` (deterministic, no LLM dep).

**Score: 100% (28/28)** as of last run.

For full pipeline eval (LLM-based), need live infra + ground truth answers.

---

## Test Strategy

- **Unit tests:** 347 in `tests/`
- **E2E tests:** 3 files (test_e2e_ohlc, test_e2e_price, test_http_price) — need live DB, excluded from CI
- **Eval:** `python evals/runner.py` — fast, no infra

**Run unit tests:**
```bash
cd backend
pytest tests/ --ignore=tests/test_e2e_ohlc.py \
              --ignore=tests/test_e2e_price.py \
              --ignore=tests/test_http_price.py
```

---

## Latency Budget (per query)

| Step | Latency |
|------|---------|
| Auth + sanitize | <50ms |
| Intent classify | <10ms |
| Embed query (Ollama GPU) | 80-300ms |
| Qdrant search | 100-300ms |
| Web search (DDG) | 1-2s (cached: <50ms) |
| LLM generate (Groq) | 1-2s |
| **Total (Groq)** | **~2-4s** |
| **Total (Ollama local)** | **~5-15s** |

---

## Known Bugs / Tech Debt

- `Dockerfile` not in repo (was removed accidentally during cleanup; AGENTS.md mentions it but file is at `backend/Dockerfile`)
- `docker-compose.yml:1` has obsolete `version: "3.8"` (warning only)
- `general_intent.py` is pattern-based, not LLM-driven — first step toward Agentic RAG
- `rag_orchestrator.py` is fixed pipeline, not agentic loop
- `web_filter.py:352` is large + fragile (DDG snippet extraction)
- No streaming response (SSE was removed in 75094ef)
- No feedback UI in frontend
- No evaluation for full RAG pipeline (only intent classifier)

---

## Intent Classifier Patterns (current)

`general_intent.py` order:
1. Casual (delegated to `strict_mode.get_casual_response()`)
2. Out-of-scope (creative tasks: pantun/resep/translate/draw/math, adversarial: ignore-previous/dev-mode/system-tag)
3. Price (keyword match: harga/tertinggi/terendah/open/close/etc)
4. Default: rag_question

Ponytail rule: patterns live here, not scattered in chat.py.

---

## Performance Tuning Knobs

- `SIMILARITY_THRESHOLD` (default 0.40) — effective for bge-m3
- `TOP_K` (5) — chunks per query
- `RATE_LIMIT_CHAT_MAX` (30) — per IP per window
- `RATE_LIMIT_WINDOW` (60s)
- `SESSION_CLEANUP_INTERVAL` (300s) — delete idle sessions
- `MAX_HISTORY_TURNS` (10) — context length
- `CHUNK_SIZE`/`CHUNK_OVERLAP` (512/50) — splitter config

---

## Quick Debugging

```bash
# Backend logs
docker compose logs backend -f

# Check if Qdrant has points
docker exec chatbot-rag-backend-1 python -c "
import json, urllib.request
r = urllib.request.urlopen('http://qdrant:6333/collections/company_knowledge_base', timeout=5)
print(json.loads(r.read())['result']['points_count'])
"

# Test embedding
docker exec chatbot-rag-backend-1 python -c "
from app.services.embedding import generate_embedding
e = generate_embedding('test')
print('dim:', len(e))
"

# Force re-seed admin
docker exec chatbot-rag-db-1 psql -U postgres -d chatbot -c "DELETE FROM users WHERE username='admin';"
docker compose restart backend
```

---

## Future: Agentic RAG (not implemented)

Current: rule-based routing (classify_intent).

Agentic upgrade path (estimated 3-5 days):
1. Wrap services as tools: `search_kb(query)`, `search_web(query)`, `lookup_price(target, date)`, `lookup_marketplace(product)`
2. Replace `classify_intent()` with LLM router (system prompt with tool descriptions)
3. Multi-step loop: `observe → decide → act` (max 3 iter)
4. Self-correction: LLM checks answer quality, regenerates if hallucinated

Tools already exist as classes — just need tool schema wrappers. **Don't rebuild from scratch.**
