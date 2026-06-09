# Chatbot RAG — Internal Knowledge Base

Chatbot berbasis **Retrieval-Augmented Generation (RAG)** untuk knowledge base internal. Mendukung PDF, DOCX, CSV, dan XLSX — 100% lokal via **Ollama + bge-m3 + qwen2.5:7b** dengan **Groq auto-fallback**.

## Tech Stack

| Layer | Teknologi |
|-------|-----------|
| Backend | FastAPI (Python 3.10) |
| Frontend | React 18 + Vite |
| Vector DB | Qdrant v1.12.1 (1024-dim Cosine) |
| Relational DB | PostgreSQL 16 |
| Emebedding | `bge-m3` via Ollama (multilingual) |
| LLM | `qwen2.5:7b` via Ollama (Groq fallback) |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Container | Docker Compose (6 services) |

## Quick Start

```bash
# 1. Prerequisites: Ollama running on host
ollama serve
ollama pull bge-m3
ollama pull qwen2.5:7b

# 2. Setup environment
cp .env.example .env
# Isi: GROQ_API_KEY=... (untuk fallback opsional)

# 3. Start all services
docker compose up --build -d

# 4. Buka browser
open http://localhost:3000
```

## Architecture

### System Architecture

```mermaid
graph TB
    subgraph "Host Machine"
        OLLAMA[Ollama Server<br/>:11434]
        subgraph "Ollama Models"
            EMD[bge-m3<br/>Embedding]
            LLM[qwen2.5:7b<br/>LLM]
        end
        DATA[./data<br/>Uploaded Files]
    end

    subgraph "Docker Compose Stack"
        FE[Frontend<br/>React + Vite<br/>:3000]
        BE[Backend<br/>FastAPI<br/>:8000]
        WK[Worker<br/>Ingestion<br/>-- polling 5s --]
        DB[(PostgreSQL<br/>:5432)]
        QD[(Qdrant<br/>:6333 gRPC<br/>:6334 HTTP)]
    end

    FE -->|/api/v1/*| BE
    BE -->|search / upsert| QD
    BE -->|CRUD| DB
    WK -->|SELECT ... FOR UPDATE| DB
    WK -->|upsert vectors| QD
    BE -->|/api/chat| OLLAMA
    WK -->|/api/embeddings| OLLAMA
    BE -->|uploads file| DATA
    WK ---|reads file| DATA
    DATA -.-|bind mount| DATA
```

### Services

| Service | Port | Platform | Role |
|---------|------|----------|------|
| `frontend` | 3000 | Node + Vite (React 18) | Web UI |
| `backend` | 8000 | Python 3.10 + FastAPI | REST API, RAG orchestration |
| `worker` | — | Python 3.10 (standalone) | Background ingestion (polling 5s) |
| `db` | 5432 | PostgreSQL 16 | Metadata, sessions, feedback, audit |
| `qdrant` | 6333/6334 | Qdrant v1.12.1 | Vector storage (1024-dim Cosine) |
| `ollama` | 11434 | Host machine (NOT containerized) | Embedding (`bge-m3`) + LLM (`qwen2.5:7b`) |

### Container Network Diagram

```mermaid
flowchart LR
    FE[":3000<br/>React"]
    BE[":8000<br/>FastAPI"]
    DB[":5432<br/>PostgreSQL"]
    QD[":6333/:6334<br/>Qdrant"]
    WK["Worker<br/>Polling"]
    OL[":11434<br/>Ollama<br/>(Host)"]
    GR["api.groq.com<br/>Groq<br/>(Cloud)"]

    FE -->|HTTP proxy| BE
    BE -->|SQLAlchemy| DB
    BE -->|gRPC| QD
    BE -->|REST API| OL
    BE -->|REST API| GR
    WK -->|poll job| DB
    WK -->|upsert vectors| QD
    WK -->|embed chunks| OL
```

### Component Architecture (Backend)

```mermaid
graph TB
    subgraph "FastAPI Application"
        RT[Routers<br/>chat.py / documents.py]
        SR[Services Layer]
        MD[Models<br/>SQLAlchemy]
        SC[Schemas<br/>Pydantic]
        CFG[Config<br/>Pydantic Settings]
    end

    subgraph "Services"
        LLM[LLM Client<br/>llm_client.py]
        EMD[Embedding<br/>embedding.py]
        QDR[Qdrant Client<br/>qdrant_client.py]
        CHK[Chunking<br/>chunking.py]
        DOCP[Document Processor<br/>document_processor.py]
        ANS[Answerability Gate<br/>answerability.py]
        STR[Structured Extractor<br/>structured_extractor.py]
        SAN[Sanitizer<br/>sanitizer.py]
        CIRC[Circuit Breaker<br/>circuit_breaker.py]
        SCH[Session Scheduler<br/>scheduler.py]
    end

    subgraph "LLM Providers"
        OLL[OllamaProvider<br/>Local qwen2.5:7b]
        GR[GroqProvider<br/>Cloud fallback]
    end

    RT --> SR
    SR --> LLM
    SR --> EMD
    SR --> QDR
    SR --> CHK
    SR --> DOCP
    SR --> ANS
    SR --> STR
    SR --> SAN
    LLM --> OLL
    LLM --> GR
    CFG -->|env vars| SR
    CFG -->|env vars| RT
```

### Arsitektur Non-Teknis (End-to-End)

```mermaid
flowchart LR
    subgraph "1. Upload Dokumen"
        A1[Admin upload<br/>PDF/DOCX/CSV/XLSX] --> A2[Worker otomatis<br/>memproses & mengindex]
    end

    subgraph "2. Pengguna Bertanya"
        B1[Karyawan mengetik<br/>pertanyaan] --> B2[Sistem cari<br/>dokumen relevan]
    end

    subgraph "3. AI Menjawab"
        B2 --> C1[AI baca dokumen<br/>yang cocok] --> C2[AI rangkum jawaban<br/>+ sebutkan sumbernya]
    end

    subgraph "4. Hasil"
        C2 --> D1[Jawaban tampil<br/>di chat + sumber<br/>dari dokumen internal]
    end
```

### Alur Sederhana

```
Pengguna Bertanya
    │
    ▼
AI Periksa: Apakah ini pertanyaan umum? (sapaan)
    ├── Ya → Jawab langsung
    │
    └── Tidak → Cari di dokumen perusahaan
              │
              ├── Ditemukan → AI baca, rangkum, sebutkan sumber dokumen
              │
              └── Tidak ditemukan → Beritahu pengguna bahwa informasi
                                    tidak tersedia di knowledge base
```

### Database Schema (PostgreSQL)

```mermaid
erDiagram
    USERS ||--o{ USER_ROLES : has
    ROLES ||--o{ USER_ROLES : assigned
    USERS ||--o{ DOCUMENTS : uploads
    USERS ||--o{ CHAT_SESSIONS : owns
    USERS ||--o{ FEEDBACK : gives
    USERS ||--o{ AUDIT_LOGS : triggers
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : contains
    DOCUMENTS ||--o{ INGESTION_JOBS : processes
    DOCUMENTS ||--o{ MESSAGE_CITATIONS : referenced
    CHAT_SESSIONS ||--o{ CHAT_MESSAGES : has
    CHAT_MESSAGES ||--o{ MESSAGE_CITATIONS : has
    CHAT_MESSAGES ||--o{ FEEDBACK : receives
    RAG_EVALUATION_CASES ||--o{ RAG_EVALUATION_RUNS : evaluated

    USERS {
        uuid id PK
        varchar email UK
        varchar name
        varchar password_hash
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    ROLES {
        uuid id PK
        varchar name UK
        text description
    }

    USER_ROLES {
        uuid user_id PK
        uuid role_id PK
    }

    DOCUMENTS {
        uuid id PK
        text original_filename
        text stored_filename
        text file_path
        varchar file_type
        varchar mime_type
        bigint size_bytes
        varchar document_hash
        varchar access_level
        varchar status
        int version
        uuid uploaded_by FK
        varchar error_code
        text error_message
        timestamp created_at
        timestamp updated_at
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        int chunk_index
        varchar text_hash
        int page_number
        varchar sheet_name
        varchar section_title
        int token_count
        uuid qdrant_point_id
        timestamp created_at
    }

    INGESTION_JOBS {
        uuid id PK
        uuid document_id FK
        varchar status
        int attempts
        int max_attempts
        varchar error_code
        text error_message
        timestamp started_at
        timestamp finished_at
        timestamp created_at
    }

    CHAT_SESSIONS {
        uuid id PK
        uuid user_id FK
        timestamp expires_at
        timestamp created_at
        timestamp updated_at
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid session_id FK
        uuid user_id FK
        varchar role
        text content
        text query_original
        text query_rewritten
        varchar confidence
        int latency_ms
        jsonb token_usage
        timestamp created_at
    }

    MESSAGE_CITATIONS {
        uuid id PK
        uuid message_id FK
        uuid chunk_id FK
        uuid document_id FK
        int quote_start
        int quote_end
        timestamp created_at
    }

    FEEDBACK {
        uuid id PK
        uuid message_id FK
        uuid user_id FK
        varchar feedback
        text comment
        timestamp created_at
    }

    AUDIT_LOGS {
        uuid id PK
        uuid actor_user_id FK
        varchar event_type
        varchar resource_type
        uuid resource_id
        varchar ip_address
        text user_agent
        jsonb metadata
        timestamp created_at
    }

    RAG_EVALUATION_CASES {
        uuid id PK
        text question
        text expected_answer
        uuid expected_document_ids
        uuid expected_chunk_ids
        varchar category
        timestamp created_at
    }

    RAG_EVALUATION_RUNS {
        uuid id PK
        uuid case_id FK
        text answer
        uuid retrieved_chunk_ids
        jsonb metrics
        timestamp created_at
    }
```

### RAG Query Sequence

```mermaid
sequenceDiagram
    participant User
    participant FE as Frontend
    participant BE as Backend (Router)
    participant LLM as LLM Service
    participant EMB as Embedding Service
    participant QD as Qdrant
    participant DB as PostgreSQL
    participant OLL as Ollama

    User->>FE: "apa itu bitcoin?"
    FE->>BE: POST /api/v1/chat/query
    activate BE

    BE->>DB: get_or_create_session()
    DB-->>BE: session_id

    BE->>BE: _sanitize(query)
    BE->>BE: _is_casual? → false

    BE->>DB: get_history()
    DB-->>BE: history (string)

    alt has history
        BE->>LLM: rewrite_query(query, history)
        LLM->>OLL: /api/chat (qwen2.5:7b)
        OLL-->>LLM: rewritten query
        LLM-->>BE: enriched_query
    else no history
        BE->>BE: skip rewrite
    end

    BE->>BE: expand_synonyms()

    BE->>EMB: generate_embedding(enriched_query)
    activate EMB
    EMB->>OLL: /api/embeddings (bge-m3)
    OLL-->>EMB: 1024-dim vector
    EMB-->>BE: query_vector
    deactivate EMB

    BE->>QD: search(top-20, score>=0.3)
    activate QD
    QD-->>BE: scored results
    deactivate QD

    BE->>BE: filter(similarity_threshold)
    BE->>QDR: rerank_chunks (skip if <=5)
    BE->>ANS: answerability gate

    alt can_answer = false
        BE-->>FE: abstain response
    else can_answer = true
        BE->>BE: format_context_with_ids(C1, C2...)
        BE->>OLL: generate_response(qwen2.5:7b)
        activate OLL
        OLL-->>BE: LLM reply with [C1][C2] citations
        deactivate OLL

        BE->>BE: validate_citations()
        alt citation invalid
            BE->>OLL: generate (retry with strict prompt)
        end

        BE->>BE: replace [C1] → [Sumber: file.pdf]
        BE->>DB: save chat_message + message_citations

        BE-->>FE: QueryResponse
    end

    deactivate BE
    FE-->>User: Display answer + sources
```

### Document Ingestion Sequence

```mermaid
sequenceDiagram
    participant Admin as Admin User
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant DISK as /data volume
    participant WK as Worker
    participant QD as Qdrant
    participant OLL as Ollama

    Admin->>FE: Upload file (PDF/DOCX/CSV/XLSX)
    FE->>BE: POST /api/v1/documents/upload
    activate BE

    BE->>BE: validate file (extension, size, MIME)
    BE->>DISK: save file as {uuid}.ext
    BE->>DB: INSERT Document(status='queued')
    BE->>DB: INSERT IngestionJob(status='queued')
    BE-->>FE: 202 Accepted {document_id, job_id}
    deactivate BE

    loop Poll every 5s
        WK->>DB: SELECT ... FOR UPDATE SKIP LOCKED
        alt has queued job
            WK->>DB: UPDATE job → 'processing'
            WK->>DISK: read file
            WK->>WK: parse_document()
            WK->>WK: chunk_document()
            WK->>OLL: generate_embeddings() (bge-m3)
            activate OLL
            OLL-->>WK: 1024-dim vectors
            deactivate OLL
            WK->>QD: batch_upsert(PointStruct)
            WK->>DB: UPDATE job → 'completed'
            WK->>DB: UPDATE document → 'completed'
        end
    end
```

### Request Processing Flow

```mermaid
flowchart TD
    REQ["POST /api/v1/chat/query"] --> SANITIZE["_sanitize()<br/>Strip zero-width chars<br/>Remove URLs<br/>Fullwidth→Halfwidth<br/>Truncate to 2000 chars"]
    SANITIZE --> PII["scan_and_redact()<br/>Redact NIK, email, phone<br/>... (inconsistent between Ollama/Groq)"]
    PII --> CASUAL{"_is_casual()"}
    CASUAL -->|"≤3 chars or<br/>casual regex"| GREETING["generate_response()<br/>System prompt only<br/>No context"]
    CASUAL -->|"substantive"| RAG["RAG Pipeline"]

    subgraph RAG["RAG Pipeline"]
        direction TB
        HIST{"history?"}
        HIST -->|no| SKIP[Skip rewrite_query]
        HIST -->|yes| RW["rewrite_query()<br/>~2-3s LLM call"]
        RW --> EXP["expand_synonyms()<br/>synonyms.json"]
        SKIP --> EXP
        EXP --> EMBED["generate_embedding()<br/>bge-m3 → 1024-dim"]
        EMBED --> SEARCH["Qdrant dense search<br/>top-20, score≥0.3"]
        SEARCH --> PROG{"0 results?"}
        PROG -->|yes| RELAX["Progressive fallback<br/>score_threshold=0.0"]
        PROG -->|found| FILTER["Filter by SIMILARITY_THRESHOLD<br/>(current: 0.55)"]
        RELAX --> RELAXED{"still 0?"}
        RELAXED -->|yes| FALLBACK["Return fallback message"]
        RELAXED -->|found| FILTER
        FILTER --> RERANK{"chunks > 5?"}
        RERANK -->|yes| RR["rerank_chunks()<br/>LLM binary relevance"]
        RERANK -->|"no (≤5)"| SKIP_RR["Skip reranker"]
        RR --> GATE["Answerability Gate<br/>can_answer? confidence?"]
        SKIP_RR --> GATE
        GATE -->|can_answer=false| ABSTAIN["Return abstain message"]
        GATE -->|can_answer=true| CTX["format_context_with_ids()<br/>C1, C2, C3..."]
        CTX --> GEN["generate_response()<br/>qwen2.5:7b LLM call"]
        GEN --> CITATION{"is_citation_valid()?"}
        CITATION -->|invalid| REGEN["Regenerate with strict prompt"]
        REGEN --> CITATION
        CITATION -->|valid| DISPLAY["Replace [C1] → [Sumber: file.pdf]"]
        DISPLAY --> SAVE["Save to DB:<br/>chat_messages<br/>message_citations"]
        SAVE --> RESP["Return QueryResponse<br/>+ reply + sources + confidence"]
    end

    GREETING --> RESP
    FALLBACK --> RESP
    ABSTAIN --> RESP
```

## API Endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/query` | RAG query (non-streaming, stable) |
| `POST` | `/api/v1/chat/stream` | SSE streaming (may break on short responses) |
| `POST` | `/api/v1/chat/fallback` | Google search (direct link if API down) |
| `POST` | `/api/v1/chat/feedback` | Thumbs up/down (`positive`/`negative`) |

### Documents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload (multipart, returns 202) |
| `GET` | `/api/v1/documents` | List (paginated: `?page=1&per_page=50`) |
| `DELETE` | `/api/v1/documents/{id}` | Soft delete + Qdrant cleanup |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | DB + Qdrant connectivity |

### Contoh Query

```bash
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "Content-Type: application/json" \
  -d '{"query":"apa itu bitcoin"}'
```

Response:
```json
{
  "session_id": "uuid",
  "reply": "Bitcoin adalah sistem uang elektronik peer-to-peer...",
  "message_id": "uuid",
  "sources": [{"file_name": "bitcoin.pdf"}],
  "confidence": "medium",
  "fallback_triggered": false,
  "out_of_context": false
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `groq` |
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b` | LLM model untuk Ollama |
| `GROQ_API_KEY` | — | Required jika `LLM_PROVIDER=groq` |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | LLM model untuk Groq |
| `EMBEDDING_MODEL` | `bge-m3` | Embedding model via Ollama |
| `EMBEDDING_DIM` | `1024` | Harus sesuai dimensi model |
| `SIMILARITY_THRESHOLD` | `0.55` | Minimum similarity score |
| `CHUNK_SIZE` | `200` | Chunk size (words) — default Docker `512` |
| `CHUNK_OVERLAP` | `25` | Chunk overlap — default Docker `50` |
| `HYBRID_TOP_K` | `20` | Max candidates dari Qdrant |
| `TOP_K` | `5` | Max chunks ke LLM context |
| `ENABLE_EXTERNAL_FALLBACK` | `false` | Google Custom Search |
| `JWT_SECRET_KEY` | `change_me` | Untuk auth (belum aktif) |

## Key Design Decisions

| Decision | Alasan |
|----------|--------|
| **Non-streaming endpoint** | SSE streaming uvicorn corrupted pada async generator pendek |
| **`native_enum=False`** | SAEnum PostgreSQL menyimpan `.name` (uppercase), tapi Python enum punya `.value` (lowercase) — solusi: VARCHAR + string literal |
| **Threshold 0.40** | `nomic-embed-text` English-optimized — score BI query rata-rata 0.50-0.58. Dengan `bge-m3` multilingual, threshold bisa naik ke 0.50+ |
| **Chunk-ID citation** | Bukan semantic similarity post-hoc. LLM diminta pakai `[C1]`, `[C2]` — divalidasi regex |
| **Ollama auto-fallback Groq** | 2 retry ke Ollama → otomatis switch ke Groq. Zero down time |
| **UUID columns** | SQLAlchemy `UUID(as_uuid=True)` return Python UUID. Schema Pydantic butuh `field_validator("id", mode="before")` untuk convert ke string |

## Dokumentasi Referensi

| File | Deskripsi |
|------|-----------|
| `docs/prd.md` | Product requirements |
| `docs/task.md` | 25 dev tasks across 5 milestones |
| `docs/audit-report.md` | Gap analysis vs PRD |
| `docs/AI_CODING_GUARDRAILS.md` | AI coding rules |
| `AGENTS.md` | Instructions for AI coding assistant |

## Developer Commands

```bash
# Dari folder backend/
make lint          # ruff check .
make format        # ruff check --fix . && black .
make typecheck     # mypy app/
make test          # python -m pytest tests/ -v
make test-cov      # with coverage report

# Docker
docker compose logs backend -f   # Backend logs
docker compose logs worker -f    # Worker logs
docker compose exec backend python -c "from app.config import SIMILARITY_THRESHOLD; print(SIMILARITY_THRESHOLD)"
```
