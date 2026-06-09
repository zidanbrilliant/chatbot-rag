# TASK — Implementation Plan Internal Knowledge Base Chatbot RAG

**Versi:** 1.0  
**Berdasarkan:** `prd.md`  
**Tujuan:** daftar pekerjaan teknis rinci untuk merealisasikan PRD secara aman, terukur, dan minim error.  
**Aturan utama:** setiap task harus memiliki acceptance criteria, test, dan rollback/mitigation jika menyentuh komponen kritis.

---

## 0. Prinsip Eksekusi

1. Jangan mengimplementasikan fitur yang tidak ada di `prd.md`.
2. Jangan menghapus fitur existing tanpa alasan teknis dan catatan migrasi.
3. Jangan hardcode secret, token, API key, host production, atau credential.
4. Setiap perubahan schema wajib melalui Alembic migration.
5. Setiap endpoint baru wajib memiliki validasi request, error handling, dan test.
6. Setiap pipeline RAG wajib dapat diobservasi melalui log dan metric.
7. Model tidak boleh menjawab pertanyaan substantif tanpa retrieval dan answerability gate.
8. Fallback Google tidak boleh otomatis untuk data internal.
9. Semua response user-facing menggunakan Bahasa Indonesia.
10. Selesaikan task berdasarkan urutan milestone kecuali ada dependency teknis yang eksplisit.

---

## Milestone 0 — Baseline Audit dan Repo Hygiene

### T0.1 Audit Struktur Repository Existing

**Tujuan:** memahami struktur project, pipeline existing, endpoint, config, dependency, dan gap terhadap PRD.

**Langkah:**

1. Baca file utama:
   - `AGENTS.md`
   - `backend/app/main.py`
   - `backend/app/config.py`
   - `backend/app/database.py`
   - `backend/app/services/*`
   - `backend/app/routers/*`
   - `backend/tests/*`
   - `frontend/package.json`
   - `docker-compose.yml`
   - `.env.example`
2. Buat catatan gap dalam `docs/audit-report.md`.
3. Identifikasi komponen yang sudah ada dan tidak perlu dibuat ulang.
4. Identifikasi komponen yang perlu refactor.

**Output:**

- `docs/audit-report.md`

**Acceptance Criteria:**

- Audit mencantumkan endpoint existing.
- Audit mencantumkan service existing.
- Audit mencantumkan mismatch terhadap PRD.
- Audit mencantumkan risiko teknis prioritas tinggi.

---

### T0.2 Tambahkan Tooling Kualitas Kode Backend

**Tujuan:** memastikan kode Python konsisten dan dapat dicek otomatis.

**Langkah:**

1. Tambahkan dependency development:
   - `ruff`
   - `black`
   - `mypy` atau `pyright`
   - `pytest-cov`
   - `pre-commit`
2. Tambahkan konfigurasi `pyproject.toml`.
3. Buat command:
   - `make lint`
   - `make format`
   - `make typecheck`
   - `make test`
4. Tambahkan pre-commit config.

**File yang mungkin berubah:**

- `backend/pyproject.toml`
- `backend/Makefile`
- `.pre-commit-config.yaml`
- `backend/requirements-dev.txt` atau dependency manager sesuai repo existing

**Acceptance Criteria:**

- `ruff check .` berjalan.
- `black --check .` berjalan.
- `pytest` berjalan.
- Dokumentasi command ditambahkan.

---

### T0.3 Tambahkan Tooling Kualitas Frontend

**Tujuan:** memastikan frontend konsisten dan tidak mudah regress.

**Langkah:**

1. Tambahkan ESLint.
2. Tambahkan Prettier.
3. Tambahkan TypeScript jika project siap migrasi; jika belum, minimal ESLint untuk JS/JSX.
4. Tambahkan script di `package.json`:
   - `lint`
   - `format`
   - `build`
   - `test` jika test framework tersedia.

**Acceptance Criteria:**

- `npm run build` berhasil.
- `npm run lint` berhasil atau mencatat issue existing di audit.
- Tidak ada dependency yang tidak diperlukan.

---

### T0.4 Rapikan Environment Configuration

**Tujuan:** semua konfigurasi critical tersedia di `.env.example` dan divalidasi saat startup.

**Langkah:**

1. Audit semua env var existing.
2. Tambahkan env var sesuai PRD:
   - `APP_ENV`
   - `DATABASE_URL`
   - `QDRANT_URL`
   - `QDRANT_GRPC_PORT`
   - `QDRANT_COLLECTION`
   - `OLLAMA_BASE_URL`
   - `EMBEDDING_MODEL`
   - `EMBEDDING_DIM`
   - `GROQ_API_KEY`
   - `GROQ_MODEL`
   - `GOOGLE_API_KEY`
   - `GOOGLE_CSE_ID`
   - `JWT_SECRET_KEY`
   - `RATE_LIMIT_WINDOW`
   - `RATE_LIMIT_CHAT_MAX`
   - `RATE_LIMIT_ADMIN_MAX`
   - `CHUNK_SIZE`
   - `CHUNK_OVERLAP`
   - `SIMILARITY_THRESHOLD`
   - `HYBRID_TOP_K`
   - `SESSION_TTL_MINUTES`
   - `SESSION_MAX_TURNS`
   - `UPLOAD_MAX_MB`
   - `ENABLE_EXTERNAL_FALLBACK`
3. Buat config loader berbasis Pydantic Settings.
4. Validasi env wajib saat startup.
5. Pastikan secret tidak tercetak di log.

**Acceptance Criteria:**

- App gagal startup dengan pesan jelas jika env wajib tidak tersedia.
- `.env.example` lengkap.
- Tidak ada secret default production.

---

## Milestone 1 — Database dan Migration Foundation

### T1.1 Pasang Alembic Migration

**Tujuan:** mengganti schema mutation manual dengan migration formal.

**Langkah:**

1. Setup Alembic di backend.
2. Hubungkan Alembic ke SQLAlchemy metadata.
3. Buat initial migration untuk schema existing.
4. Hapus atau deprecate query `ALTER TABLE ...` manual saat startup setelah migration siap.
5. Tambahkan command:
   - `alembic upgrade head`
   - `alembic revision --autogenerate -m "message"`

**Acceptance Criteria:**

- Database kosong dapat dibuat dengan `alembic upgrade head`.
- Aplikasi tidak menjalankan schema mutation manual yang tidak terdokumentasi.
- Migration dapat dijalankan berulang tanpa error.

---

### T1.2 Buat/Perbarui Model Database Sesuai PRD

**Tujuan:** menyiapkan table untuk user, role, dokumen, chunk, ingestion, chat, citation, feedback, audit, dan evaluasi.

**Tabel:**

1. `users`
2. `roles`
3. `user_roles`
4. `documents`
5. `document_chunks`
6. `ingestion_jobs`
7. `chat_sessions`
8. `chat_messages`
9. `message_citations`
10. `feedback`
11. `audit_logs`
12. `rag_evaluation_cases`
13. `rag_evaluation_runs`

**Langkah:**

1. Buat SQLAlchemy models.
2. Tambahkan indexes untuk:
   - `documents.status`
   - `documents.document_hash`
   - `document_chunks.document_id`
   - `chat_messages.session_id`
   - `audit_logs.event_type`
   - `audit_logs.created_at`
3. Tambahkan foreign key dan cascade yang aman.
4. Buat migration.
5. Tambahkan unit test model minimal.

**Acceptance Criteria:**

- Semua tabel dibuat via migration.
- FK valid.
- Index terbentuk.
- Test database model pass.

---

### T1.3 Buat Repository Layer

**Tujuan:** menghindari query database tersebar di router/service.

**Repository minimal:**

1. `UserRepository`
2. `DocumentRepository`
3. `ChunkRepository`
4. `IngestionJobRepository`
5. `ChatSessionRepository`
6. `ChatMessageRepository`
7. `FeedbackRepository`
8. `AuditLogRepository`
9. `EvaluationRepository`

**Acceptance Criteria:**

- Router tidak melakukan query SQL langsung kecuali sangat sederhana dan terdokumentasi.
- Repository memiliki test untuk operasi create/read/update dasar.

---

## Milestone 2 — Security Foundation

### T2.1 Implementasi Auth Minimum

**Tujuan:** mengganti kondisi “No auth” untuk readiness produksi.

**Langkah:**

1. Buat endpoint:
   - `POST /api/v1/auth/login`
   - `POST /api/v1/auth/refresh` jika refresh token dipakai
   - `GET /api/v1/auth/me`
2. Gunakan JWT.
3. Gunakan password hash `argon2` atau `bcrypt` jika local auth.
4. Buat dependency FastAPI:
   - `get_current_user`
   - `require_role`
5. Tambahkan seed role dasar.

**Acceptance Criteria:**

- User valid bisa login.
- Token invalid ditolak 401.
- Endpoint protected tidak bisa diakses tanpa token.
- Password tidak disimpan plaintext.

---

### T2.2 Implementasi RBAC

**Tujuan:** memastikan endpoint admin dan retrieval menghormati role.

**Langkah:**

1. Definisikan role:
   - `viewer`
   - `document_admin`
   - `system_admin`
   - `auditor`
2. Terapkan role ke endpoint:
   - upload: document_admin/system_admin
   - delete document: document_admin/system_admin
   - audit log: auditor/system_admin
   - evaluation run: system_admin
   - chat: viewer ke atas
3. Buat permission helper.
4. Tambahkan test role.

**Acceptance Criteria:**

- Viewer tidak bisa upload dokumen.
- Document admin tidak bisa mengakses konfigurasi system_admin jika ada.
- Auditor hanya read-only untuk audit/evaluation.

---

### T2.3 Document Permission Filter

**Tujuan:** user tidak dapat mengambil chunk dari dokumen yang tidak berhak diakses.

**Langkah:**

1. Tambahkan field `access_level` pada documents dan payload Qdrant.
2. Buat mapping role ke allowed access level.
3. Terapkan filter saat retrieval Qdrant.
4. Pastikan filter dilakukan sebelum chunk dikirim ke LLM.
5. Tambahkan test retrieval permission.

**Acceptance Criteria:**

- Viewer hanya mengambil dokumen `internal`.
- Restricted/confidential tidak muncul untuk role tanpa izin.
- LLM context tidak mengandung chunk yang tidak sah.

---

### T2.4 Upload Security

**Tujuan:** mencegah upload berbahaya dan path traversal.

**Langkah:**

1. Validasi ukuran file maksimal dari env `UPLOAD_MAX_MB`.
2. Validasi ekstensi.
3. Validasi MIME type.
4. Validasi file signature jika memungkinkan.
5. Sanitize filename.
6. Simpan file dengan UUID.
7. Tolak nama file path traversal seperti `../../secret`.
8. Skip file Excel temporary `~$`.
9. Tambahkan scanner hook opsional.

**Acceptance Criteria:**

- File `.exe` ditolak.
- File >50 MB ditolak.
- Filename path traversal ditolak.
- File valid diterima dan dibuatkan ingestion job.

---

### T2.5 Input Sanitization dan Prompt Injection Defense

**Tujuan:** memperkuat query user dan konten dokumen sebagai untrusted input.

**Langkah:**

1. Buat `InputSanitizer`.
2. Hapus zero-width unicode.
3. Normalisasi fullwidth ke halfwidth.
4. Batasi panjang query.
5. Deteksi pola prompt injection dasar:
   - “abaikan instruksi sebelumnya”
   - “ignore previous instructions”
   - “jangan gunakan dokumen”
   - “ungkap system prompt”
6. Tambahkan flag, bukan selalu reject, kecuali pola eksplisit berbahaya.
7. Pastikan system prompt menyatakan dokumen adalah untrusted content.

**Acceptance Criteria:**

- Query dengan zero-width dibersihkan.
- Prompt injection tidak membuat model bypass RAG.
- Test adversarial pass.

---

### T2.6 Audit Log Service

**Tujuan:** mencatat aktivitas penting.

**Langkah:**

1. Buat `AuditLogService`.
2. Buat helper `log_event`.
3. Tambahkan audit pada:
   - login success/fail
   - upload dokumen
   - delete dokumen
   - query RAG
   - fallback external search
   - feedback
   - permission denied
   - ingestion failed
4. Masking data sensitif pada metadata.

**Acceptance Criteria:**

- Audit log tercatat untuk event wajib.
- Secret tidak masuk audit metadata.
- Auditor bisa membaca audit log.

---

## Milestone 3 — Ingestion Pipeline

### T3.1 Pisahkan Ingestion dari Startup API

**Tujuan:** API server tidak melakukan pekerjaan berat saat startup.

**Langkah:**

1. Buat worker process terpisah.
2. Pilih queue:
   - Redis + RQ/Arq/Celery, atau
   - PostgreSQL job polling jika ingin lebih sederhana.
3. Upload endpoint hanya menyimpan file dan membuat job.
4. Worker mengambil job dan memproses.
5. Startup auto-ingestion existing boleh dipertahankan hanya sebagai command manual, bukan default production.

**Acceptance Criteria:**

- API bisa startup tanpa memproses semua file `/data`.
- Upload return 202 cepat.
- Worker memproses job secara async.

---

### T3.2 Document Parser Service

**Tujuan:** parsing file konsisten per format.

**Langkah:**

1. Buat interface `DocumentParser`.
2. Implementasi parser:
   - `PdfParser`
   - `DocxParser`
   - `CsvParser`
   - `XlsxParser`
3. Output parser harus berupa struktur:

```python
ParsedDocument(
    document_id=..., 
    sections=[ParsedSection(...)]
)
```

4. Simpan page/sheet/section metadata.
5. Tangani file corrupt dengan error code.

**Acceptance Criteria:**

- PDF valid terparse.
- DOCX valid terparse.
- CSV valid terparse.
- XLSX valid terparse.
- File corrupt menghasilkan status failed, bukan crash.

---

### T3.3 Chunking Service Adaptif

**Tujuan:** menghasilkan chunk yang tidak merusak struktur dokumen.

**Langkah:**

1. Buat `ChunkingService`.
2. Gunakan recursive splitter untuk teks naratif.
3. Gunakan heading-aware chunking untuk DOCX/SOP.
4. Gunakan row-aware chunking untuk tabel.
5. Tambahkan token count.
6. Tambahkan text hash.
7. Hindari chunk kosong.

**Acceptance Criteria:**

- Chunk punya metadata lengkap.
- Row tabel tidak terpotong.
- Chunk kosong tidak masuk Qdrant.
- Unit test chunking pass.

---

### T3.4 Embedding Service Hardening

**Tujuan:** embedding stabil, cacheable, dan measurable.

**Langkah:**

1. Buat abstraction `EmbeddingProvider`.
2. Implementasi `OllamaEmbeddingProvider`.
3. Tambahkan timeout.
4. Tambahkan retry exponential backoff.
5. Tambahkan cache untuk query embedding.
6. Tambahkan batch embedding untuk ingestion.
7. Validasi dimensi embedding sama dengan `EMBEDDING_DIM`.
8. Jangan mengubah signature fungsi yang memiliki cache tanpa update semua caller.

**Acceptance Criteria:**

- Embedding gagal ditangani terkontrol.
- Dimensi mismatch menghasilkan error jelas.
- Batch embedding berjalan.
- Unit test provider dengan mock pass.

---

### T3.5 Qdrant Upsert dan Delete Service

**Tujuan:** vector operation terpusat dan aman.

**Langkah:**

1. Buat `VectorStoreService`.
2. Pastikan collection dibuat jika belum ada.
3. Validasi vector size.
4. Upsert point dengan payload lengkap.
5. Delete vector berdasarkan `document_id`.
6. Gunakan gRPC jika env mendukung.
7. Tambahkan retry terbatas.

**Acceptance Criteria:**

- Upsert berhasil untuk chunk valid.
- Delete dokumen menghapus vector terkait.
- Qdrant down menghasilkan error terkontrol.

---

### T3.6 Idempotent Ingestion

**Tujuan:** mencegah duplikasi dokumen dan vector.

**Langkah:**

1. Hitung SHA256 file.
2. Jika hash sudah ada dan status completed, jangan reingest kecuali force reindex.
3. Jika reindex, naikkan version.
4. Delete vector versi lama atau tandai inactive sesuai strategi.
5. Simpan job attempt.

**Acceptance Criteria:**

- Upload file sama tidak membuat duplikasi vector.
- Force reindex terdokumentasi.
- Job retry tidak membuat chunk ganda.

---

## Milestone 4 — RAG Query Pipeline

### T4.1 RAG Orchestrator

**Tujuan:** membuat pipeline utama terstruktur.

**Langkah:**

1. Buat `RagOrchestrator`.
2. Pecah tahap:
   - sanitize
   - classify intent
   - load session
   - rewrite query
   - expand synonym
   - retrieve
   - rerank
   - build context
   - answerability check
   - generate
   - validate citation
   - save response
3. Setiap tahap mengembalikan telemetry.
4. Error setiap tahap ditangani.

**Acceptance Criteria:**

- Query RAG berjalan end-to-end.
- Setiap tahap memiliki log latency.
- Failure satu tahap tidak membuat unhandled exception.

---

### T4.2 Intent Classifier

**Tujuan:** membedakan greeting, RAG, tabular, fallback, out-of-scope, dan unsafe.

**Langkah:**

1. Buat rule-based classifier awal.
2. Tambahkan test untuk:
   - “halo”
   - “halo apa isi SOP cuti?”
   - pertanyaan angka dari CSV
   - pertanyaan out-of-scope
   - fallback request
3. Pastikan greeting tidak terlalu agresif.

**Acceptance Criteria:**

- “halo” classified sebagai casual.
- “halo apa isi SOP cuti?” classified sebagai RAG, bukan casual.
- Query ≤3 chars tidak otomatis casual jika mengandung konteks penting.

---

### T4.3 Query Rewrite Service

**Tujuan:** membuat follow-up question menjadi standalone.

**Langkah:**

1. Gunakan history maksimal `SESSION_MAX_TURNS`.
2. Prompt rewrite melarang penambahan fakta baru.
3. Simpan query original dan rewritten.
4. Jika rewrite gagal, gunakan query original.

**Acceptance Criteria:**

- Follow-up “kalau prosedurnya bagaimana?” dapat direwrite dengan konteks sebelumnya.
- Rewrite tidak menambahkan informasi yang tidak ada.
- Test dengan mock LLM pass.

---

### T4.4 Synonym Expansion Service

**Tujuan:** meningkatkan recall tanpa mengubah maksud query.

**Langkah:**

1. Gunakan `synonyms.json`.
2. Buat schema synonym:

```json
{
  "cuti": ["leave", "izin tidak masuk"],
  "SOP": ["prosedur", "standard operating procedure"]
}
```

3. Tambahkan cache file.
4. Tambahkan env untuk enable/disable.
5. Tambahkan test.

**Acceptance Criteria:**

- Sinonim domain ditambahkan ke query internal.
- Query tidak membengkak ekstrem.
- Service aman jika file synonym kosong/rusak.

---

### T4.5 Hybrid Retrieval

**Tujuan:** menggabungkan semantic search dan keyword/sparse search.

**Langkah:**

1. Dense search via Qdrant vector.
2. Keyword search minimal via PostgreSQL full-text atau Qdrant sparse jika tersedia.
3. Gabungkan hasil dengan Reciprocal Rank Fusion.
4. Terapkan permission filter.
5. Ambil kandidat top `HYBRID_TOP_K`.
6. Simpan score mentah dan fused score.

**Acceptance Criteria:**

- Istilah spesifik seperti nomor SOP/tanggal dapat ditemukan.
- Dense semantic query tetap bekerja.
- Permission filter berlaku.

---

### T4.6 Reranker Service

**Tujuan:** menyaring chunk kandidat agar context lebih relevan.

**Langkah:**

1. Buat interface `RerankerProvider`.
2. Implementasi awal:
   - LLM binary relevance existing, atau
   - cross-encoder jika dependency disetujui.
3. Input: query + kandidat chunk.
4. Output: sorted chunk + rerank_score + reason optional.
5. Tambahkan timeout.
6. Jika reranker gagal, fallback ke fused score dengan warning log.

**Acceptance Criteria:**

- Chunk tidak relevan tersaring.
- Reranker timeout tidak membuat request crash.
- Rerank score tersimpan dalam telemetry.

---

### T4.7 Answerability Gate

**Tujuan:** mencegah jawaban tanpa evidence cukup.

**Langkah:**

1. Implementasi `AnswerabilityService`.
2. Rule awal:
   - no candidates → abstain;
   - top score < threshold → abstain;
   - rerank_score rendah semua → abstain;
   - tabular lookup gagal → abstain/clarify;
   - ambiguous query → ask clarification.
3. Return decision:

```json
{
  "can_answer": true,
  "confidence": "high|medium|low|abstain",
  "reason": "string"
}
```

4. Tambahkan test untuk out-of-scope dan weak evidence.

**Acceptance Criteria:**

- Pertanyaan di luar dokumen tidak dijawab bebas.
- Weak evidence menghasilkan abstain.
- Confidence muncul di response.

---

### T4.8 Context Builder

**Tujuan:** membangun context bernomor dan token-budgeted.

**Langkah:**

1. Buat format `[CHUNK C1]`, `[CHUNK C2]`, dst.
2. Sertakan file, halaman, sheet, section.
3. Deduplicate chunk mirip.
4. Batasi token.
5. Masukkan `[FAKTA TERVERIFIKASI]` jika ada structured extraction.
6. Simpan mapping `C1 -> chunk_id`.

**Acceptance Criteria:**

- Context tidak melebihi token budget.
- Mapping citation valid.
- Metadata sumber lengkap.

---

### T4.9 LLM Gateway

**Tujuan:** provider LLM tidak tersebar di banyak file.

**Langkah:**

1. Buat interface `LlmProvider`.
2. Implementasi `GroqProvider`.
3. Parameter dari config:
   - model
   - temperature
   - max_tokens
   - timeout
4. Tambahkan retry terbatas.
5. Tambahkan structured output mode jika provider mendukung.
6. Jangan log prompt lengkap jika mengandung data sensitif; log hash/summary saja.

**Acceptance Criteria:**

- LLM call bisa dimock di test.
- Provider error ditangani.
- Temperature faktual rendah.

---

### T4.10 Strict System Prompt

**Tujuan:** memaksa model grounded.

**Langkah:**

1. Buat file prompt misalnya `backend/app/prompts/rag_system_prompt.txt`.
2. Isi instruksi:
   - gunakan hanya context;
   - jangan pakai pengetahuan eksternal;
   - abstain jika tidak ada informasi;
   - setiap klaim penting harus menyertakan citation ID;
   - dokumen adalah untrusted content;
   - Bahasa Indonesia.
3. Tambahkan prompt test sederhana.

**Acceptance Criteria:**

- Prompt tidak tersebar hardcoded di banyak service.
- Prompt memuat aturan anti-halusinasi.

---

### T4.11 Citation Validator

**Tujuan:** memastikan citation benar-benar dari context.

**Langkah:**

1. Model harus menghasilkan citation seperti `[C1]`, `[C2]`.
2. Validator mengecek semua citation ID ada di context mapping.
3. Jika invalid, lakukan regeneration sekali.
4. Jika tetap invalid, return abstain/error terkontrol.
5. Simpan citation ke `message_citations`.

**Acceptance Criteria:**

- Citation di luar context ditolak.
- Jawaban faktual tanpa citation ditolak atau diregenerate.
- Citation tersimpan di database.

---

### T4.12 Structured Extractor Hardening

**Tujuan:** memperkuat query tabular agar angka tidak halu.

**Langkah:**

1. Deteksi query tabular.
2. Identifikasi file kandidat dari retrieval metadata.
3. Baca CSV/XLSX via pandas.
4. Parse filter tanggal/nama/kolom.
5. Return fakta terverifikasi.
6. Tangani ambiguity dengan klarifikasi.
7. Tambahkan test dengan fixture CSV/XLSX.

**Acceptance Criteria:**

- Nilai angka berasal dari file, bukan LLM.
- Jika kolom tidak ditemukan, sistem berkata tidak ditemukan.
- Row-aware formatting tetap berjalan.

---

### T4.13 Session Management Hardening

**Tujuan:** session aman dan konsisten.

**Langkah:**

1. Session TTL dari env.
2. Simpan last N turns.
3. Gunakan row lock saat update session jika concurrency.
4. Jika expired, buat session baru dan return `session_id` baru.
5. Frontend wajib update session id.

**Acceptance Criteria:**

- Expired session tidak crash.
- Concurrent message tidak merusak history.
- Test session expiry pass.

---

## Milestone 5 — API Endpoints

### T5.1 Chat Query Endpoint

**Endpoint:** `POST /api/v1/chat/query`

**Langkah:**

1. Validasi request schema.
2. Require auth minimal viewer.
3. Terapkan rate limit.
4. Panggil `RagOrchestrator`.
5. Return response sesuai PRD.
6. Audit query.

**Acceptance Criteria:**

- Query valid return answer/citation/confidence.
- Query out-of-scope return abstain.
- Unauthorized return 401.
- Rate limit return 429.

---

### T5.2 Chat Stream Endpoint

**Endpoint:** `POST /api/v1/chat/stream`

**Langkah:**

1. Gunakan SSE.
2. Event minimal:
   - `metadata`
   - `token`
   - `citation`
   - `fallback_offer`
   - `done`
   - `error`
3. Jangan stream jawaban sebelum answerability gate selesai.
4. Simpan final message ke database.

**Acceptance Criteria:**

- First event metadata valid.
- Token streaming berjalan.
- Error event tidak memutus tanpa pesan.

---

### T5.3 Feedback Endpoint

**Endpoint:** `POST /api/v1/chat/feedback`

**Langkah:**

1. Validasi `message_id`.
2. Validasi feedback `positive|negative`.
3. Optional comment.
4. Simpan ke database.
5. Audit event.

**Acceptance Criteria:**

- Feedback valid tersimpan.
- Message tidak ditemukan return 404.
- Feedback invalid return 422.

---

### T5.4 Fallback Endpoint

**Endpoint:** `POST /api/v1/chat/fallback`

**Langkah:**

1. Cek env `ENABLE_EXTERNAL_FALLBACK`.
2. Require explicit user request.
3. Sanitasi query.
4. Jangan kirim data rahasia.
5. Return hasil dengan label external.
6. Audit event.

**Acceptance Criteria:**

- Jika fallback disabled, return pesan jelas.
- Hasil diberi label eksternal.
- Fallback tidak dipakai diam-diam oleh query internal.

---

### T5.5 Document Upload Endpoint

**Endpoint:** `POST /api/v1/documents/upload`

**Langkah:**

1. Require role document_admin/system_admin.
2. Validasi file.
3. Simpan file.
4. Buat document row.
5. Buat ingestion job.
6. Return 202.
7. Audit upload.

**Acceptance Criteria:**

- Upload valid return job id.
- Upload invalid ditolak.
- Job muncul di database.

---

### T5.6 Document List dan Detail Endpoint

**Endpoint:**

- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`

**Langkah:**

1. Pagination `page` dan `per_page` max 200.
2. Filter status/file_type/q.
3. Role-based visibility.
4. Return ingestion status.

**Acceptance Criteria:**

- Pagination bekerja.
- Viewer tidak melihat dokumen restricted/confidential jika tidak berhak.
- Detail menampilkan error ingestion jika ada.

---

### T5.7 Document Delete Endpoint

**Endpoint:** `DELETE /api/v1/documents/{document_id}`

**Langkah:**

1. Require role document_admin/system_admin.
2. Soft delete document.
3. Delete vector dari Qdrant berdasarkan `document_id`.
4. Mark chunks inactive/deleted.
5. Audit delete.

**Acceptance Criteria:**

- Dokumen deleted tidak muncul di retrieval.
- Vector terkait terhapus.
- Delete dokumen tidak ditemukan return 404.

---

### T5.8 Health, Readiness, Liveness

**Endpoint:**

- `GET /health`
- `GET /ready`
- `GET /live`

**Langkah:**

1. `/live`: process alive.
2. `/health`: basic app info.
3. `/ready`: cek PostgreSQL, Qdrant, dan config wajib.

**Acceptance Criteria:**

- Qdrant down membuat `/ready` gagal.
- PostgreSQL down membuat `/ready` gagal.
- `/live` tetap valid jika process alive.

---

## Milestone 6 — Frontend

### T6.1 Auth UI

**Tujuan:** user dapat login dan token tersimpan aman.

**Langkah:**

1. Buat halaman login.
2. Simpan token dengan mekanisme aman sesuai target deployment.
3. Tambahkan interceptor API untuk auth header.
4. Redirect jika 401.

**Acceptance Criteria:**

- Login berhasil.
- Token invalid memaksa login ulang.
- Endpoint admin disembunyikan untuk role tidak sesuai.

---

### T6.2 Chat UI

**Tujuan:** user dapat bertanya dan melihat citation.

**Langkah:**

1. Buat input chat.
2. Tampilkan jawaban.
3. Tampilkan citation:
   - file name
   - page/sheet/section
4. Tampilkan confidence.
5. Tampilkan abstain message.
6. Tampilkan loading state.
7. Tampilkan error state.
8. Tambahkan feedback thumbs up/down.

**Acceptance Criteria:**

- Jawaban dan citation tampil jelas.
- Abstain tidak terlihat seperti error teknis.
- Feedback terkirim.

---

### T6.3 Streaming Chat UI

**Tujuan:** perceived latency lebih baik.

**Langkah:**

1. Integrasikan SSE endpoint.
2. Tampilkan token streaming.
3. Setelah done, tampilkan citation.
4. Tangani error event.
5. Fallback ke non-streaming jika SSE gagal.

**Acceptance Criteria:**

- Streaming berjalan tanpa menggandakan pesan.
- Error SSE terlihat jelas.
- Citation tetap muncul setelah done.

---

### T6.4 Document Management UI

**Tujuan:** admin dapat upload dan memonitor dokumen.

**Langkah:**

1. Halaman list dokumen.
2. Upload form.
3. Progress/status ingestion.
4. Detail dokumen.
5. Delete action dengan confirm dialog.
6. Filter status dan tipe file.

**Acceptance Criteria:**

- Upload valid membuat job.
- Status ingestion berubah.
- Delete meminta konfirmasi.

---

### T6.5 Audit dan Evaluation UI

**Tujuan:** auditor/system admin dapat memantau kualitas.

**Langkah:**

1. Halaman audit log read-only.
2. Filter by event type/date.
3. Halaman evaluation run.
4. Tampilkan metric RAG.

**Acceptance Criteria:**

- Auditor bisa membuka audit log.
- Viewer tidak bisa membuka audit log.
- Evaluation metric tampil.

---

## Milestone 7 — Observability dan Evaluation

### T7.1 Structured Logging

**Tujuan:** semua request penting dapat dianalisis.

**Langkah:**

1. Gunakan JSON log.
2. Tambahkan request ID.
3. Log latency setiap tahap RAG.
4. Masking data sensitif.
5. Jangan log full secret/prompt sensitif.

**Acceptance Criteria:**

- Setiap request punya request_id.
- RAG telemetry tercatat.
- Secret tidak muncul di log.

---

### T7.2 Metrics Endpoint

**Tujuan:** expose metric untuk monitoring.

**Langkah:**

1. Tambahkan Prometheus metrics atau format metric lain.
2. Metric minimal:
   - request count
   - error count
   - latency histogram
   - retrieval latency
   - LLM latency
   - ingestion status count
   - citation validation failure
   - abstain rate
3. Dokumentasikan metric.

**Acceptance Criteria:**

- Metrics dapat di-scrape.
- Latency histogram ada.
- Error rate terukur.

---

### T7.3 Evaluation Dataset

**Tujuan:** mengukur kualitas RAG secara objektif.

**Langkah:**

1. Buat fixture dataset minimal 100 case.
2. Kategori:
   - factual narrative
   - SOP/procedure
   - tabular
   - out-of-scope
   - prompt injection
3. Simpan expected source document/chunk jika tersedia.
4. Buat loader dataset.

**Acceptance Criteria:**

- Dataset dapat dibaca runner.
- Setiap case punya category.
- Out-of-scope case tersedia.

---

### T7.4 Evaluation Runner

**Tujuan:** menjalankan query dan menghitung metric.

**Langkah:**

1. Buat script `python -m app.evaluation.run`.
2. Untuk setiap case:
   - kirim query ke RAG pipeline;
   - simpan retrieved chunk;
   - simpan answer;
   - hitung metric.
3. Metric:
   - Recall@5
   - Recall@10
   - MRR
   - citation accuracy
   - abstain accuracy
   - latency p50/p95
4. Simpan ke `rag_evaluation_runs`.

**Acceptance Criteria:**

- Runner berjalan dari CLI.
- Report tersimpan.
- Metric ringkas tampil di terminal.

---

### T7.5 Feedback Analytics

**Tujuan:** feedback user dapat digunakan untuk perbaikan.

**Langkah:**

1. Buat endpoint admin untuk ringkasan feedback.
2. Group by positive/negative.
3. Tampilkan query dengan negative feedback.
4. Hubungkan dengan retrieved chunks dan citation.

**Acceptance Criteria:**

- Admin bisa melihat negative feedback.
- Feedback terhubung ke message dan citation.

---

## Milestone 8 — Testing dan Quality Gate

### T8.1 Unit Tests

**Cakupan wajib:**

1. config loader;
2. input sanitizer;
3. intent classifier;
4. synonym expansion;
5. chunking;
6. structured extractor;
7. answerability gate;
8. citation validator;
9. repository layer;
10. permission helper.

**Acceptance Criteria:**

- Coverage minimum 70% untuk backend core services.
- Test deterministic.

---

### T8.2 Integration Tests

**Cakupan wajib:**

1. upload dokumen → job dibuat;
2. worker ingest → Qdrant upsert;
3. query RAG → citation valid;
4. delete dokumen → vector hilang;
5. auth/RBAC;
6. fallback disabled/enabled.

**Acceptance Criteria:**

- Integration test dapat dijalankan via Docker Compose test stack.
- Tidak bergantung pada API key production.

---

### T8.3 Contract Tests API

**Tujuan:** response schema tidak berubah sembarangan.

**Langkah:**

1. Gunakan FastAPI OpenAPI schema.
2. Buat test untuk endpoint utama.
3. Validasi status code.
4. Validasi response field wajib.

**Acceptance Criteria:**

- Breaking change terdeteksi.
- Response schema sesuai PRD.

---

### T8.4 Security Tests

**Cakupan wajib:**

1. unauthorized access;
2. role forbidden;
3. upload invalid;
4. path traversal;
5. rate limiting;
6. prompt injection adversarial;
7. secret not logged.

**Acceptance Criteria:**

- Semua skenario security utama pass.
- Permission denied masuk audit log.

---

### T8.5 Load Test

**Tujuan:** validasi target p95.

**Langkah:**

1. Siapkan dataset dokumen uji.
2. Simulasi concurrent user.
3. Ukur:
   - p50/p95 latency;
   - error rate;
   - throughput;
   - CPU/memory;
   - Qdrant latency;
   - LLM latency.
4. Buat report `docs/load-test-report.md`.

**Acceptance Criteria:**

- p95 query RAG < 8 detik pada environment target atau ada catatan bottleneck.
- Error rate terukur.

---

## Milestone 9 — DevOps dan Production Readiness

### T9.1 Docker Compose Hardening

**Tujuan:** stack lokal mudah dijalankan dan mendekati production.

**Langkah:**

1. Pisahkan service:
   - backend
   - frontend
   - worker
   - postgres
   - qdrant
   - redis jika dipakai
2. Tambahkan healthcheck.
3. Tambahkan volume persistent.
4. Tambahkan env example.
5. Jangan mount secret ke image.

**Acceptance Criteria:**

- Fresh clone + `.env` valid dapat menjalankan stack.
- Worker berjalan terpisah.
- Healthcheck aktif.

---

### T9.2 CI Pipeline

**Tujuan:** setiap push/PR menjalankan quality gate.

**Langkah:**

1. Setup GitHub Actions/GitLab CI sesuai platform.
2. Jobs:
   - backend lint
   - backend test
   - backend typecheck
   - frontend lint
   - frontend build
   - docker build
   - dependency scan jika tersedia
3. Cache dependency.

**Acceptance Criteria:**

- PR gagal jika test gagal.
- Docker image dapat dibuild.

---

### T9.3 Backup dan Restore Plan

**Tujuan:** data dapat dipulihkan.

**Langkah:**

1. Dokumentasikan backup PostgreSQL.
2. Dokumentasikan Qdrant snapshot atau reindex strategy.
3. Dokumentasikan backup uploaded files/object storage.
4. Buat restore drill minimal lokal.

**Acceptance Criteria:**

- `docs/backup-restore.md` tersedia.
- Restore lokal berhasil dari backup sample.

---

### T9.4 Deployment Documentation

**Tujuan:** deployment reproducible.

**Langkah:**

1. Buat `docs/deployment.md`.
2. Isi:
   - prerequisite;
   - env var;
   - Docker Compose command;
   - migration command;
   - health check;
   - rollback;
   - common errors.

**Acceptance Criteria:**

- Developer baru bisa menjalankan project mengikuti dokumentasi.
- Common error Ollama/Qdrant/Postgres terdokumentasi.

---

## 10. Release Checklist

Sebelum release, pastikan:

- [ ] Semua env var wajib tersedia.
- [ ] Migration berjalan dari database kosong.
- [ ] Docker Compose fresh build berhasil.
- [ ] Backend lint pass.
- [ ] Backend test pass.
- [ ] Frontend build pass.
- [ ] Auth aktif.
- [ ] RBAC endpoint admin aktif.
- [ ] Upload invalid ditolak.
- [ ] Qdrant permission filter aktif.
- [ ] RAG menjawab dengan citation valid.
- [ ] Out-of-scope menghasilkan abstain.
- [ ] Citation validator aktif.
- [ ] Structured extractor untuk CSV/XLSX pass.
- [ ] Fallback eksternal disabled by default atau opt-in.
- [ ] Audit log aktif.
- [ ] Metrics aktif.
- [ ] Evaluation runner berjalan.
- [ ] No hardcoded secret.
- [ ] Load test report tersedia.
- [ ] Backup/restore doc tersedia.

---

## 11. Definition of Done per Pull Request

Setiap PR harus memenuhi:

1. menyebut task ID dari file ini;
2. menjelaskan perubahan ringkas;
3. menyebut file yang diubah;
4. menyertakan test yang dijalankan;
5. tidak menambah scope di luar PRD;
6. tidak meninggalkan TODO kritis tanpa issue;
7. tidak menurunkan security;
8. tidak memperkenalkan secret;
9. tidak membuat endpoint admin tanpa RBAC;
10. tidak membuat LLM menjawab tanpa RAG gate.

---

## 12. Urutan Implementasi yang Disarankan

Urutan paling aman:

1. T0.1 Audit.
2. T0.2 Backend tooling.
3. T0.4 Env config.
4. T1.1 Alembic.
5. T1.2 DB models.
6. T2.1 Auth.
7. T2.2 RBAC.
8. T2.6 Audit log.
9. T3.1 Worker ingestion.
10. T3.2 Parser.
11. T3.3 Chunking.
12. T3.4 Embedding.
13. T3.5 Qdrant service.
14. T4.1 RAG orchestrator.
15. T4.5 Hybrid retrieval.
16. T4.7 Answerability gate.
17. T4.8 Context builder.
18. T4.9 LLM gateway.
19. T4.11 Citation validator.
20. T5 endpoint hardening.
21. T6 frontend.
22. T7 observability/evaluation.
23. T8 tests.
24. T9 production readiness.

---

## 13. Catatan Penting untuk Developer

1. Jangan mengejar “jawaban selalu ada”. Untuk RAG internal, jawaban abstain lebih benar daripada jawaban halu.
2. Jangan membuat Google fallback sebagai jalan pintas untuk retrieval yang buruk.
3. Jangan mengirim chunk yang tidak lolos permission ke LLM.
4. Jangan menyimpan seluruh prompt berisi data sensitif ke log.
5. Jangan mengganti embedding model tanpa reindex plan.
6. Jangan mengubah threshold tanpa evaluation report.
7. Jangan menghapus audit log untuk memperbaiki error.
8. Jangan menggabungkan ingestion berat ke startup API production.
