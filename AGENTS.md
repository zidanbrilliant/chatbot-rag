# AGENTS.md — Internal Knowledge Base Chatbot (RAG)

## Status

Implementation in progress. Backend (FastAPI) and frontend (React) scaffolding complete. All 25 tasks from `docs/task.md` implemented.

## Reference documents

| File | Purpose |
|---|---|
| `docs/prd-chatbot.md` | Full PRD: goals, requirements (FR-01 through FR-08), architecture, milestones, KPIs |
| `docs/spec.md` | DB schemas (Qdrant + SQL), 5 REST API endpoint specs |
| `docs/task.md` | 25 concrete dev tasks across 5 milestones (all checked) |

These three files **are the sole truth**. All documents are in **Bahasa Indonesia**.

## Planned tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | **FastAPI** (Python) | REST API |
| Frontend | **React** (Vite) | |
| Vector DB | **Qdrant** | Collection: `company_knowledge_base`, 768-dim, Cosine |
| Relational DB | **PostgreSQL** | SQLAlchemy ORM |
| Embedding | `nomic-embed-text` via Ollama | 768 dimensions |
| Chunking | **LangChain** `RecursiveCharacterTextSplitter` | 512 tokens, 50 overlap |
| Container | **Docker Compose** | Backend + Frontend + Qdrant + PostgreSQL |
| Fallback search | Google Custom Search JSON API | |

## Architecture summary

Single FastAPI backend serving a web frontend. Three core pipelines:
1. **RAG Query:** sanitize → embed → Qdrant search (top-k 3–5, threshold ≥ 0.5) → build prompt → Groq API → return with citations
2. **Document Ingestion:** upload → parse → chunk → embed → upsert Qdrant
3. **Fallback/Guardrails:** below-threshold → offer Google Search; out-of-context → reject politely

## Project structure

```
backend/
  app/
    main.py              — FastAPI app, startup (DB tables + Qdrant collection)
    config.py            — All env-var-driven config
    database.py          — SQLAlchemy engine + session
    models/              — document, chat (SQLAlchemy ORM)
    schemas/             — chat, document (Pydantic)
    routers/             — chat, documents (API endpoints)
    services/            — qdrant_client, groq_client, embedding, document_processor, chunking
    core/                — logging (JSON structured)
  tests/                 — test_chunking, test_parsers, test_integration
  requirements.txt
  Dockerfile
frontend/
  src/
    components/          — Chat.jsx, AdminPanel.jsx
    api.js               — Axios API client
    App.jsx              — Tab-based layout (Chat / Admin Panel)
    App.css
  Dockerfile
  package.json
docker-compose.yml       — backend + frontend + db (PostgreSQL) + qdrant
.env.example
```

## Key constraints

- **No auth in MVP.** SSO deferred to Phase 2.
- Admin panel must be internal-network/VPN only (SEC-05).
- Secrets (API keys) in env vars or secret manager — never hardcoded (SEC-02).
- P95 response ≤ 5 sec, doc ingestion ≤ 60 sec, ≥ 200 concurrent users.
- Chunk size 512 tokens, overlap 50 tokens (both configurable via env).
- Session expires after 30 min, keeps last 10 turns.
- File upload max 50 MB, formats: PDF, DOCX, XLSX, CSV.
- All critical config (thresholds, model name, timeout, chunk size) must be env-variable driven — no rebuild needed.
- **Business context boundary:** only documents in `/data` directory are in-scope. Anything else is out-of-context.

## API endpoints (from spec.md)

- `POST /api/v1/chat/query` — RAG query (session_id optional, auto-creates session)
- `POST /api/v1/chat/fallback` — Google Search fallback
- `POST /api/v1/documents/upload` — multipart upload (202 Accepted)
- `GET /api/v1/documents` — list documents
- `DELETE /api/v1/documents/{document_id}` — delete doc + vectors

## Developer commands

```bash
# Start all services
docker compose up --build

# Run backend tests
cd backend && python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_chunking.py -v
```
