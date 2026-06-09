# Audit Report — Baseline Repository Check

**Tanggal audit:** 2026-06-08  
**Referensi:** `prd.md` v1.0, `task.md` v1.0, `AGENTS.md`  
**Tujuan:** Mendokumentasikan kondisi existing, gap terhadap PRD, dan risiko teknis prioritas tinggi.

---

## 1. Struktur Repository

```
chatbot-rag/
├── AGENTS.md                         # Dev guide (143 lines)
├── docker-compose.yml                # 4 service (71 lines)
├── .env.example                      # 12 env vars (12 lines)
├── .gitignore
├── knowledge.md                      # Referensi eksternal (Kotaemon — tidak relevan)
├── docs/
│   ├── prd.md                        # Product requirements (1205 lines)
│   ├── spec.md                       # DB + API spec (155 lines)
│   ├── task.md                       # 25 tasks / 9 milestones (1548 lines)
│   └── AI_CODING_GUARDRAILS.md       # AI coding rules (409 lines)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt              # 21 packages
│   ├── alembic/                      # Scaffold ada, 0 migration tertulis
│   │   ├── env.py
│   │   ├── alembic.ini
│   │   └── versions/                 # KOSONG
│   └── app/
│       ├── main.py                   # FastAPI entry (170 lines)
│       ├── config.py                 # 21 env vars via os.getenv (25 lines)
│       ├── database.py               # SQLAlchemy engine (16 lines)
│       ├── core/logging.py           # JSON formatter (34 lines)
│       ├── models/
│       │   ├── chat.py               # ChatSession + ChatHistory (25 lines)
│       │   └── document.py           # Document (23 lines)
│       ├── schemas/
│       │   ├── chat.py               # Pydantic models (46 lines)
│       │   └── document.py           # Pydantic models (23 lines)
│       ├── routers/
│       │   ├── chat.py               # 4 endpoint + SELURUH pipeline RAG (524 lines)
│       │   └── documents.py          # 3 endpoint (111 lines)
│       └── services/
│           ├── groq_client.py        # LLM, rerank, citation, synonym (319 lines)
│           ├── embedding.py          # Ollama embedding (53 lines)
│           ├── qdrant_client.py      # Qdrant singleton (33 lines)
│           ├── ingestion.py          # File ingest (102 lines)
│           ├── document_processor.py # PDF/DOCX/CSV/XLSX parser (91 lines)
│           ├── chunking.py           # Recursive + tabular splitter (71 lines)
│           ├── structured_extractor.py # CSV/XLSX fact lookup (155 lines)
│           ├── circuit_breaker.py    # Circuit breaker (57 lines)
│           ├── sanitizer.py          # PII detection (44 lines)
│           └── scheduler.py          # Session cleanup (48 lines)
├── backend/tests/
│   ├── test_chunking.py              # 4 test (28 lines)
│   ├── test_parsers.py               # 2 test (35 lines)
│   └── test_integration.py           # Import check only (22 lines)
├── frontend/
│   ├── Dockerfile
│   ├── package.json                  # React 18 + Vite (20 lines)
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                   # Tab Chat + Admin (27 lines)
│       ├── api.js                    # Axios client (77 lines)
│       └── components/
│           ├── Chat.jsx              # SSE chat UI (188 lines)
│           └── AdminPanel.jsx        # Upload/list/delete (78 lines)
└── data/                             # Uploaded files (gitignored)
```

**Total kode backend:** ~1.830 lines (tanpa test/docs)  
**Total kode frontend:** ~370 lines  
**Total test:** 85 lines (3 file, 7 test)

---

## 2. Endpoint Existing

### REST API

| # | Method | Path | Router | Status | Catatan |
|---|--------|------|--------|--------|---------|
| 1 | `POST` | `/api/v1/chat/query` | `routers/chat.py:142` | **ADA** | RAG pipeline lengkap inline |
| 2 | `POST` | `/api/v1/chat/stream` | `routers/chat.py:304` | **ADA** | SSE streaming |
| 3 | `POST` | `/api/v1/chat/fallback` | `routers/chat.py:475` | **ADA** | Google Search eksternal |
| 4 | `POST` | `/api/v1/chat/feedback` | `routers/chat.py:510` | **ADA** | Feedback disimpan di chat_history.feedback |
| 5 | `POST` | `/api/v1/documents/upload` | `routers/documents.py:33` | **ADA** | Multipart, BackgroundTasks |
| 6 | `GET` | `/api/v1/documents` | `routers/documents.py:64` | **ADA** | Pagination via `page`/`per_page` |
| 7 | `GET` | `/api/v1/documents/{id}` | — | **TIDAK ADA** | PRD Section 18.2 mewajibkan |
| 8 | `DELETE` | `/api/v1/documents/{id}` | `routers/documents.py:87` | **ADA** | Soft delete + Qdrant delete |
| 9 | `GET` | `/health` | `main.py:149` | **ADA** | Cek DB + Qdrant |
| 10 | `GET` | `/ready` | — | **TIDAK ADA** | PRD Section 18.3 mewajibkan |
| 11 | `GET` | `/live` | — | **TIDAK ADA** | PRD Section 18.3 mewajibkan |

### Auth & Admin (PRD Section 18)

| # | Method | Path | Status |
|---|--------|------|--------|
| 12 | `POST` | `/api/v1/auth/login` | **TIDAK ADA** |
| 13 | `POST` | `/api/v1/auth/refresh` | **TIDAK ADA** |
| 14 | `GET` | `/api/v1/auth/me` | **TIDAK ADA** |
| 15 | `POST` | `/api/v1/admin/evaluations/run` | **TIDAK ADA** |
| 16 | `GET` | `/api/v1/admin/evaluations/{run_id}` | **TIDAK ADA** |

**Resume:** 8/14 endpoint PRD sudah ada, 6 missing.

---

## 3. Service Existing

| Service | File | Lines | Deskripsi |
|---------|------|-------|-----------|
| **RAG Pipeline** | `routers/chat.py` | 524 | Seluruh pipeline di dalam router (anti-pattern) |
| **Groq Client** | `services/groq_client.py` | 319 | rewrite, rerank, format_context, synonyms, citation, generate, stream |
| **Structured Extractor** | `services/structured_extractor.py` | 155 | CSV/XLSX lookup via pandas + `[FAKTA TERVERIFIKASI]` |
| **Ingestion** | `services/ingestion.py` | 102 | Parse → chunk → embed → upsert (via BackgroundTasks) |
| **Document Processor** | `services/document_processor.py` | 91 | PDF (pdfplumber), DOCX (python-docx), CSV/XLSX (pandas) |
| **Chunking** | `services/chunking.py` | 71 | RecursiveCharacterTextSplitter + row-aware tabular |
| **Circuit Breaker** | `services/circuit_breaker.py` | 57 | CLOSED/OPEN/HALF_OPEN untuk Groq & Google |
| **Embedding** | `services/embedding.py` | 53 | Ollama, 3x retry, LRU cache, batch via ThreadPoolExecutor |
| **Scheduler** | `services/scheduler.py` | 48 | Session cleanup daemon |
| **Sanitizer** | `services/sanitizer.py` | 44 | Deteksi PII (NIK, email, phone) — bukan input sanitizer |
| **Qdrant Client** | `services/qdrant_client.py` | 33 | Singleton, gRPC, ensure_collection |
| **Logging** | `core/logging.py` | 34 | JSON formatter |

### Service yang diwajibkan PRD tapi TIDAK ADA

| Service | Referensi | Deskripsi |
|---------|-----------|-----------|
| `RagOrchestrator` | T4.1 | Orchestrator pipeline terstruktur |
| `IntentClassifier` | T4.2 | Klasifikasi greeting/RAG/tabular/out-of-scope/unsafe |
| `AnswerabilityService` | T4.7 | Gate evidence cukup/tidak |
| `CitationValidator` | T4.11 | Validasi citation via chunk ID |
| `HybridRetrievalService` | T4.5 | Dense + sparse/BM25 + RRF fusion |
| `LlmProvider` (interface) | T4.9 | Abstraction layer LLM |
| `EmbeddingProvider` (interface) | T3.4 | Abstraction layer embedding |
| `VectorStoreService` | T3.5 | Abstraction layer Qdrant |
| `AuditLogService` | T2.6 | Pencatatan audit event |
| `AuthService` | T2.1 | JWT login, token management |
| `PermissionService` | T2.3 | Document access level filter |
| `UserRepository` | T1.3 | Abstraction layer user DB |
| `DocumentRepository` | T1.3 | Abstraction layer document DB |
| `ChunkRepository` | T1.3 | Abstraction layer chunk DB |
| `IngestionJobRepository` | T1.3 | Abstraction layer ingestion DB |
| `ChatSessionRepository` | T1.3 | Abstraction layer session DB |
| `ChatMessageRepository` | T1.3 | Abstraction layer message DB |
| `FeedbackRepository` | T1.3 | Abstraction layer feedback DB |
| `AuditLogRepository` | T1.3 | Abstraction layer audit DB |
| `EvaluationRepository` | T1.3 | Abstraction layer evaluation DB |

---

## 4. Database — Mismatch terhadap PRD

### Tabel PRD vs Existing

| # | Tabel PRD | Status | Catatan |
|---|-----------|--------|---------|
| 1 | `users` | **MISSING** | Diperlukan untuk auth |
| 2 | `roles` | **MISSING** | Diperlukan untuk RBAC |
| 3 | `user_roles` | **MISSING** | Many-to-many |
| 4 | `documents` | **PARTIAL** | Hanya 5 kolom; PRD mewajibkan 16+ kolom (original_filename, stored_filename, file_path, file_type, mime_type, document_hash, access_level, status enum 7 nilai, version, uploaded_by, error_code, error_message, updated_at) |
| 5 | `document_chunks` | **MISSING** | Tidak ada metadata chunk tersimpan di PG |
| 6 | `ingestion_jobs` | **MISSING** | Tidak ada tracking job ingestion |
| 7 | `chat_sessions` | **PARTIAL** | Tidak ada user_id, expires_at (hanya created_at/updated_at) |
| 8 | `chat_messages` | **PARTIAL** | Ada sebagai `chat_history`; missing: user_id, query_original, query_rewritten, confidence, latency_ms, token_usage |
| 9 | `message_citations` | **MISSING** | Citation disimpan inline di reply, bukan di tabel |
| 10 | `feedback` | **PARTIAL** | Hanya kolom `feedback` di `chat_history`; missing: tabel terpisah dengan user_id, comment |
| 11 | `audit_logs` | **MISSING** | Tidak ada audit logging sama sekali |
| 12 | `rag_evaluation_cases` | **MISSING** | Tidak ada dataset evaluasi |
| 13 | `rag_evaluation_runs` | **MISSING** | Tidak ada runner evaluasi |

**Resume:** 11/13 tabel belum ada. 3 tabel yang ada bersifat minimal dan tidak sesuai spesifikasi PRD.

### Migration

- Alembic scaffold ada (`backend/alembic/`) tetapi **0 migration**.
- `main.py:128-136` menjalankan `ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS feedback` manual di setiap startup — melanggar PRD Section 16.
- `main.py:118` memanggil `Base.metadata.create_all()` — tidak versioned, tidak bisa rollback.

---

## 5. RAG Pipeline — Mismatch terhadap PRD

### Alur PRD vs Existing

| Tahap PRD | Status | Implementasi | Gap |
|-----------|--------|-------------|-----|
| Auth / RBAC | **TIDAK ADA** | — | Semua request anonymous |
| Rate limit | **ADA** | `main.py:46-61` | IP-based, configurable |
| Input sanitization | **PARTIAL** | `routers/chat.py` inline | Hanya zero-width, HTML, URL, prompt injection pattern; tidak ada intent-aware sanitization |
| Intent classification | **MINIMAL** | `_is_casual()` 8 regex | Tidak ada klasifikasi `tabular_lookup`, `out_of_scope`, `unsafe_or_policy_violation` |
| Session/history loading | **ADA** | `get_or_create_session()` / `get_history()` | Session expires 30 menit |
| Query rewrite | **ADA** | `groq_client.py:rewrite_query()` | Hanya untuk query >3 kata dengan history |
| Synonym expansion | **ADA** | `groq_client.py:expand_synonyms()` | File `synonyms.json` belum ditemukan |
| Query embedding | **ADA** | `embedding.py:generate_embedding()` | Ollama, retry, LRU cache |
| Hybrid retrieval | **TIDAK ADA** | Hanya dense vector via Qdrant | Tidak ada sparse/keyword/BM25, tidak ada RRF fusion |
| Permission filter | **TIDAK ADA** | — | Semua chunk bisa diakses semua user |
| Reranking | **ADA (LLM)** | `groq_client.py:rerank_chunks()` | Binary relevance via Groq; PRD merekomendasikan cross-encoder |
| Context builder | **ADA** | `groq_client.py:format_context()` | Token-budgeted, format berbeda dari PRD |
| Answerability gate | **TIDAK ADA** | Hanya threshold + rerank filter | Tidak ada keputusan terstruktur (high/medium/low/abstain) |
| LLM generation | **ADA** | `groq_client.py:generate_response()` | Groq, temp 0.3, max_tokens 1024 |
| Citation validation | **SALAH** | `groq_client.py:insert_citations()` | Pakai semantic similarity post-hoc — PRD Section 9.11 eksplisit melarang ini. Wajib chunk-ID-based. |
| Save chat history | **ADA** | Simpan user + assistant message | Disimpan di `chat_history` |
| Structured extraction | **ADA** | `structured_extractor.py` | CSV/XLSX lookup via pandas + `[FAKTA TERVERIFIKASI]` |

### Pelanggaran PRD Kritis di RAG Pipeline

1. **Citation dibuat post-hoc via semantic similarity** (`groq_client.py:169-242`). PRD Section 9.11: "Citation tidak boleh dibuat hanya berdasarkan kemiripan semantic setelah jawaban selesai. Citation harus diikat pada chunk ID yang tersedia dalam context."
2. **Tidak ada answerability gate** — sistem tetap menjawab meski evidence lemah.
3. **521 baris pipeline di router** — melanggar separation of concerns.
4. **System prompt longgar** — tidak memaksa model grounded pada context, memperbolehkan "ngobrol santai".
5. **Response schema berbeda dari PRD** — field `reply` vs PRD `answer`, `sources` vs PRD `citations`, tidak ada `confidence` dan `latency_ms`.

---

## 6. Keamanan — Gap Terhadap PRD

| Area | PRD Req | Status | Gap |
|------|---------|--------|-----|
| **Auth** | JWT + login endpoint | **TIDAK ADA** | Semua endpoint publik |
| **RBAC** | 4 role: viewer, document_admin, system_admin, auditor | **TIDAK ADA** | Admin panel terbuka untuk semua |
| **Permission filter** | Filter access_level di Qdrant | **TIDAK ADA** | Semua user lihat semua dokumen |
| **Upload security** | MIME, signature, UUID path | **PARTIAL** | Ekstensi + UUID path ada; MIME/signature/malware scan tidak ada |
| **Secret management** | .env only, no hardcode | **OK** | Tidak ada secret hardcoded |
| **Sanitize filename** | XSS prevention | **OK** | `html.escape` + regex sanitize |
| **Prompt injection defense** | Zero-width removal, pattern detection | **PARTIAL** | Pattern dasar ada; system prompt masih longgar; document-as-data tidak enforced |
| **Audit log** | 9 event type wajib | **TIDAK ADA** | Tidak ada audit log sama sekali |
| **CORS** | Strict origin | **OK** | Configurable via `CORS_ORIGINS` |
| **Rate limit** | 30/min chat, 15/min admin | **OK** | IP-based, stale cleanup |

---

## 7. Frontend — Gap Terhadap PRD

| Fitur PRD | Status | Catatan |
|-----------|--------|---------|
| Halaman login | **TIDAK ADA** | PRD Section 19.1 |
| Chat input+output | **ADA** | `Chat.jsx` (188 lines) |
| SSE streaming | **ADA** | Dengan fallback ke non-streaming |
| Citation display | **PARTIAL** | Hanya nama file; tidak ada halaman/sheet/section |
| Confidence label | **TIDAK ADA** | Response backend belum punya field ini |
| Abstain message display | **PARTIAL** | `out_of_context` flag, tapi UI tidak spesifik |
| Feedback thumbs up/down | **TIDAK ADA** | `api.js` tidak ada fungsi `sendFeedback` |
| Daftar dokumen | **ADA** | `AdminPanel.jsx` |
| Upload dokumen | **ADA** | `AdminPanel.jsx` |
| Status ingestion | **ADA** | Color-coded (PROCESSING/INDEXED/FAILED) |
| Detail dokumen | **TIDAK ADA** | Endpoint `GET /documents/{id}` belum ada |
| Delete dokumen | **ADA** | Dengan konfirmasi window.confirm |
| Audit log UI | **TIDAK ADA** | Endpoint belum ada |
| Evaluation dashboard | **TIDAK ADA** | Endpoint belum ada |
| Pagination | **TIDAK ADA** | Backend support, frontend tidak kirim `page`/`per_page` |
| Auth interceptor | **TIDAK ADA** | Tidak ada token management |
| Role-based UI hiding | **TIDAK ADA** | Admin panel visible untuk semua |

---

## 8. Test Coverage

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_chunking.py` | 4 | Basic chunking, size, empty, single sentence |
| `test_parsers.py` | 2 | CSV parse, unsupported extension |
| `test_integration.py` | 1 | Import checks only |

**Total: 7 unit test. 0 integration/contract/security test.**

Area tanpa test:
- Router (chat, documents)
- Embedding (retry, timeout, dimension mismatch)
- Qdrant (upsert, delete, search, permission filter)
- Groq client (rewrite, rerank, generate, stream, citation)
- Structured extractor
- Sanitizer (PII, input sanitization)
- Circuit breaker
- Session management
- Rate limiter
- Config loader
- Intent classifier
- Synonym expansion
- Answerability gate
- Citation validator

---

## 9. Risiko Teknis Prioritas Tinggi

### R1 — Arsitektur: RAG Pipeline Monolithic (KRITIS)
**File:** `backend/app/routers/chat.py` (524 lines)  
Seluruh pipeline RAG ada di dalam fungsi router `chat_query` dan `chat_stream`. Ini membuat:
- Tidak bisa unit test per tahap
- Sulit dimodifikasi tanpa risiko regresi
- Melanggar separation of concerns yang diwajibkan PRD
- `AI_CODING_GUARDRAILS.md` Section 5.2 melarang "menggabungkan service ingestion dan service query dalam satu fungsi besar"

### R2 — Citation Validator Salah secara Fundamental (KRITIS)
**File:** `backend/app/services/groq_client.py:169-242`  
`insert_citations()` menggunakan semantic similarity post-hoc (embed kalimat jawaban → cosine match ke chunk vector). PRD Section 9.11 dan `AI_CODING_GUARDRAILS.md` Section 8 eksplisit melarang pendekatan ini. Citation wajib berbasis chunk ID dari context builder.

### R3 — Tidak Ada Security Sama Sekali (KRITIS)
Tidak ada authentication, authorization, RBAC, atau permission filtering. Siapa pun bisa:
- Upload dokumen
- Melihat/menghapus dokumen
- Mengakses admin panel
- Mengirim query tanpa rate limit (meski rate limiter ada di middleware)

### R4 — Tidak Ada Answerability Gate (TINGGI)
Sistem tidak punya keputusan terstruktur apakah evidence cukup untuk menjawab. Hanya mengandalkan threshold + rerank filter. PRD Section 9.8 mewajibkan gate dengan output `{can_answer, confidence, reason}`.

### R5 — Tidak Ada Audit Log (TINGGI)
PRD Section 12.6 mewajibkan audit untuk: login, upload, delete, query, fallback, feedback, permission denied, ingestion failed. Tidak ada implementasi sama sekali.

### R6 — Ingestion di API Process (TINGGI)
Upload menggunakan `BackgroundTasks` FastAPI yang berjalan di process API yang sama. Dokumen besar akan mengonsumsi CPU/memori API server. PRD dan `AI_CODING_GUARDRAILS.md` Section 5.2 melarang parsing dokumen di request thread. Task T3.1 mewajibkan worker terpisah.

### R7 — Tidak Ada Hybrid Retrieval (TINGGI)
Hanya dense vector search via Qdrant. Tidak ada sparse/keyword/BM25. PRD Section 9.6 mewajibkan hybrid retrieval dengan Reciprocal Rank Fusion.

### R8 — Schema Migration Tidak Versioned (MEDIUM)
`main.py:118` pakai `Base.metadata.create_all()` dan `main.py:128-136` jalankan `ALTER TABLE` manual. Tidak bisa rollback, tidak versioned, tidak auditable. Alembic scaffold ada tapi 0 migration.

### R9 — Embedding Model Suboptimal untuk Bahasa Indonesia (MEDIUM)
`nomic-embed-text` adalah model English-optimized. Similarity score untuk query BI terhadap dokumen EN hanya ~0.58–0.61. Threshold diturunkan ke 0.55 sebagai kompromi empiris. Perlu benchmark multilingual embedding model.

### R10 — System Prompt Tidak Cukup Ketat (MEDIUM)
System prompt (`routers/chat.py:31-46`) memperbolehkan "ngobrol santai" dan tidak memaksa model untuk:
- Abstain jika informasi tidak ada di context
- Menyertakan citation chunk ID
- Memperlakukan dokumen sebagai untrusted content

### R11 — 0 Test Coverage pada Service Core (MEDIUM)
Hanya 7 unit test. Tidak ada test untuk embedding, retrieval, reranking, citation, ingestion, auth, RBAC, sanitizer, atau endpoint. PRD mewajibkan 70% coverage minimum.

---

## 10. Dependency dan Konfigurasi

### `.env.example` — Gap (12 vars vs 26+ di PRD)

Variabel yang **ada** di `.env.example`: `GROQ_API_KEY`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`, `TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `SESSION_TIMEOUT_MINUTES`, `MAX_HISTORY_TURNS`, `MAX_FILE_SIZE_MB`, `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`

Variabel yang **tidak ada** di `.env.example` (diwajibkan PRD Section 22):
- `APP_ENV`
- `DATABASE_URL`
- `QDRANT_URL`
- `QDRANT_GRPC_PORT`
- `QDRANT_COLLECTION`
- `OLLAMA_BASE_URL`
- `EMBEDDING_DIM`
- `JWT_SECRET_KEY`
- `RATE_LIMIT_WINDOW`
- `RATE_LIMIT_CHAT_MAX`
- `RATE_LIMIT_ADMIN_MAX`
- `SESSION_TTL_MINUTES`
- `SESSION_MAX_TURNS`
- `UPLOAD_MAX_MB`
- `ENABLE_EXTERNAL_FALLBACK`

### `docker-compose.yml` — Gap

- Tidak ada worker service terpisah
- Tidak ada Redis service
- Backend healthcheck tidak ada
- Frontend healthcheck tidak ada
- Backend `depends_on` Qdrant hanya `service_started` (bukan `service_healthy`)
- Tidak ada restart policy
- Tidak ada production profile
- Volume persistent untuk uploaded files hanya bind mount `./data`

---

## 11. Rencana Tindak Lanjut

Berdasarkan `task.md` Section 12 (Urutan Implementasi Disarankan):

| Prioritas | Task | Deskripsi |
|-----------|------|-----------|
| **P0** | T1.1 | Setup Alembic + initial migration |
| **P0** | T1.2 | Buat 11 tabel database sesuai PRD |
| **P0** | T2.1 | Implementasi Auth JWT |
| **P0** | T2.2 | Implementasi RBAC 4 role |
| **P0** | T2.6 | Audit log service |
| **P1** | T4.1 | Ekstrak RAG pipeline ke RagOrchestrator |
| **P1** | T4.7 | Answerability gate |
| **P1** | T4.11 | Citation validator (chunk-ID based) |
| **P1** | T4.5 | Hybrid retrieval (dense + sparse) |
| **P1** | T3.1 | Worker ingestion terpisah |
| **P1** | T5.8 | `/ready` + `/live` endpoint |
| **P2** | T4.2 | Intent classifier |
| **P2** | T7.3 / T7.4 | Evaluation dataset + runner |
| **P2** | T0.2 | Code quality tooling (ruff, black, mypy) |
| **P2** | T8.1 / T8.2 | Test suite (target 70% coverage) |
| **P3** | T6.1-T6.5 | Frontend auth, feedback, confidence UI |
| **P3** | T9.2 | CI pipeline |

---

## 12. Catatan untuk Developer

1. Jangan mengerjakan task di luar urutan milestone tanpa alasan dependency eksplisit.
2. Jangan memperbaiki "citation validator" dengan patch kecil — perlu rewrite full sesuai PRD.
3. Jangan menambah fitur sebelum auth/RBAC selesai.
4. System prompt existing harus diganti dengan prompt ketat yang sesuai `AI_CODING_GUARDRAILS.md` Section 7.
5. `knowledge.md` tidak relevan dengan project ini — abaikan sebagai referensi.
6. Jangan pernah menurunkan threshold similarity tanpa evaluation report baru.
