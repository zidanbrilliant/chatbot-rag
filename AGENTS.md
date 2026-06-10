# AGENTS.md — Internal Knowledge Base Chatbot (RAG)

## Reference documents

| File | Purpose |
|---|---|
| `docs/prd.md` | Full PRD (goals, architecture, requirements, milestones) |
| `docs/task.md` | 25 dev tasks across 5 milestones |
| `docs/audit-report.md` | Baseline gap analysis vs PRD |
| `docs/AI_CODING_GUARDRAILS.md` | AI coding rules — read before modifying code |

All docs in **Bahasa Indonesia**. PRD + task.md are the source of truth.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.10) |
| Frontend | React 18 (Vite) — no auth in MVP |
| Vector DB | Qdrant v1.12.1, collection `company_knowledge_base`, 768-dim Cosine |
| Relational DB | PostgreSQL 16 (SQLAlchemy ORM) |
| Embedding | `nomic-embed-text` via Ollama (host machine, NOT containerized) |
| LLM | Ollama (`qwen2.5:7b`) with automatic Groq fallback |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Container | Docker Compose (5 services: backend, frontend, db, qdrant, worker) |

## Quick start

```bash
# Prerequisites: Ollama running on host with OLLAMA_HOST=0.0.0.0
ollama pull nomic-embed-text
ollama pull qwen2.5:7b

# Create .env (copy from .env.example, fill GROQ_API_KEY for fallback)
cp .env.example .env

# Start
docker compose up --build -d        # 5 services
docker compose down                 # stop, keep data
docker compose down -v              # stop + wipe ALL data
```

## Architecture (key facts an agent would miss)

### LLM Provider abstraction
- Config at `backend/app/services/llm_client.py` — `OllamaProvider` + `GroqProvider` + factory `get_llm()`
- Switch via env `LLM_PROVIDER=ollama|groq` (default: ollama)
- **Ollama auto-falls back to Groq** after 2 failures — no crash if Ollama is down
- `qwen3.5:4b` is a **thinking model** (slow, 29s greeting) — use `qwen2.5:7b` instead
- `qwen-2.5-32b` on Groq is **decommissioned** — use `llama-3.1-8b-instant`

### RAG pipeline latency (per query, on CPU)
- rewrite_query: 2-3s (LLM call, skipped if no history)
- embed query: 0.08s
- rerank_chunks: skipped if ≤5 candidates, else 5-8s (LLM call)
- generate_response: 5-15s (LLM call with context)
- **~10-25s total** with Ollama, **~8-40s** if falling back to Groq

### Embedding model threshold
- `dengcao/Qwen3-Embedding-0.6B` is the primary embedding model — outputs 1024 dims. It is highly optimized for Bahasa Indonesia.
- **Effective threshold: 0.40** (not the default 0.55 in config).
- If switching models, a full Qdrant re-index (`docker compose down -v`) is mandatory.

### SSE streaming is broken
- uvicorn has chunked-encoding issues with short async generators via `StreamingResponse`
- **Frontend uses non-streaming** `POST /chat/query` — stable and reliable
- SSE `POST /chat/stream` exists but may fail on casual/greeting path

### SAEnum gotcha
- Postgres ENUM stores names (uppercase `PROCESSING`), Python values are lowercase (`processing`)
- Models use `SAEnum(..., native_enum=False, length=20)` — stored as VARCHAR
- **ALWAYS pass string literals** (`status="processing"`) not enum members (`DocumentStatus.PROCESSING`)

### UUID columns ≠ strings
- SQLAlchemy `UUID(as_uuid=True)` returns Python `uuid.UUID` objects — NOT strings
- Pydantic schema fields typed `str` will reject UUIDs → add `@field_validator("id", mode="before")` to convert
- `response_model.message_id=str(assistant_msg.id)` — must convert explicitly

### Citation system (chunk-ID based)
- `format_context_with_ids()` returns `(context_text, chunk_mapping)` — mapping is `{"C1": {...}, "C2": {...}}`
- System prompt rule 9: LLM must use `[C1]`, `[C2]` for citations
- `validate_citations()` replaces `[C1]` with `[Sumber: file.pdf]` for user display
- `is_citation_valid()` checks all `[CX]` exist in mapping — if invalid, regenerate once

### Ingestion worker (separate process)
- `docker compose` includes a 5th service: **worker** — polls `ingestion_jobs` table every 5s
- Upload creates `Document(status="queued")` + `IngestionJob` — worker picks up and processes
- Auto-ingestion on startup also queues jobs (does NOT process directly)
- Worker uses `SELECT ... FOR UPDATE SKIP LOCKED` for concurrency safety
- Worker runs `backend/app/worker.py` (standalone, not via FastAPI)

## API endpoints

```
POST /api/v1/chat/query       — RAG query (non-streaming, stable)
POST /api/v1/chat/stream      — SSE streaming (may break on short responses)
POST /api/v1/chat/fallback    — Google search (direct link if API unavailable)
POST /api/v1/chat/feedback    — thumbs up/down
POST /api/v1/documents/upload — multipart upload (202, worker ingestion)
GET  /api/v1/documents        — list (paginated: ?page=1&per_page=50, max 200)
DELETE /api/v1/documents/{id} — soft delete + Qdrant vector delete
GET  /health                  — DB + Qdrant connectivity
```

## Developer commands (run from `backend/`)

```bash
# Code quality
make lint          # ruff check .
make format        # ruff check --fix . && black .
make typecheck     # mypy app/
make test          # python -m pytest tests/ -v
make test-cov      # with coverage report

# Alembic migrations
python -c "from alembic.config import Config; from alembic import command; cfg=Config('alembic.ini'); command.upgrade(cfg,'head')"

# Debug inside container
docker compose exec backend python -c "from app.config import SIMILARITY_THRESHOLD; print(SIMILARITY_THRESHOLD)"
docker compose logs backend -f
docker compose logs worker -f
```

- Tests must run from `backend/` directory (use `sys.path.insert`)
- `test_integration.py` is import checks only — safe without infra
- `mypy app/` may timeout locally; add `--ignore-missing-imports` to config

## Environment variables (critical ones)

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | ollama | `ollama` or `groq` |
| `OLLAMA_LLM_MODEL` | qwen2.5:7b | Must NOT be a thinking model |
| `GROQ_API_KEY` | — | Required only for Groq fallback/provider |
| `SIMILARITY_THRESHOLD` | 0.55 | **Actually needs 0.40** for nomic-embed-text |
| `ENABLE_EXTERNAL_FALLBACK` | false | Google CSE; direct link provided if API unavailable |
| `EMBEDDING_MODEL` | dengcao/Qwen3-Embedding-0.6B | Do NOT change without reindex plan |
| `EMBEDDING_DIM` | 1024 | Must match Qdrant collection |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512/50 | Docker; outside Docker defaults are 200/25 |

## Session and chat quirks

- Expired session → server silently creates **new session** (client must update `session_id`)
- `_is_casual()` requires exact end-of-string match — "halo apa kabar" is NOT casual
- `get_history()` returns a **string** (not `list[dict]`) — format: `"User: ...\nAssistant: ..."`
- `generate_embedding()` has `@lru_cache(maxsize=1000)` — signature changes silently bypass cache

## Known issues (not yet fixed)

| Issue | Workaround |
|-------|------------|
| Out-of-scope queries not abstained | Need T4.2 Intent Classifier |
| Structured extractor rarely triggered | Threshold too low, chunks always found |
| Google CSE returns 403 | Enable API in Google Cloud Console, or use direct link |
| SSE chunked encoding broken | Frontend uses non-streaming endpoint |
| `MessageCitation` may skip invalid UUIDs | Silently skipped (acceptable for citation validation) |

## Worker quirks

- **FOR UPDATE deadlock**: `run_worker()` main loop acquires `SELECT ... FOR UPDATE SKIP LOCKED` on a job row, then calls `process_job()` which opens its OWN session and tries to UPDATE the same row. Two sessions compete for the same row lock → deadlock. Fixed by `db.commit()` in main loop BEFORE calling process_job, releasing the lock.
- **SAEnum case sensitivity**: `native_enum=False` stores enum **names** (uppercase `QUEUED`, `PROCESSING`, `COMPLETED`), NOT values (lowercase `queued`). This means:
  - Raw SQL `INSERT ... 'queued'` stores lowercase → worker filter `WHERE status = 'QUEUED'` WON'T MATCH
  - **ALWAYS uppercase status values in raw SQL**: `'QUEUED'`, `'COMPLETED'`
  - SAEnum + str enum automatically convert string literals to uppercase when inserting via ORM
  - The worker `process_job()` uses `IngestionJobStatus.QUEUED` (enum member) → SAEnum serializes to `'QUEUED'` correctly
- **Auto-ingest duplicates**: Every container restart scans `/data/` and creates new Document+IngestionJob records. The skip filter `status == COMPLETED` only skips completed files. Failed/queued files get duplicated on every restart. Fixed filter to also skip existing QUEUED/PROCESSING records.
