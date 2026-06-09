# PRD — Internal Knowledge Base Chatbot RAG

**Versi:** 1.0  
**Status:** Ready for implementation  
**Bahasa utama:** Bahasa Indonesia  
**Tipe produk:** Internal Knowledge Base Chatbot berbasis Retrieval-Augmented Generation (RAG)  
**Target pengguna:** karyawan/internal user, admin dokumen, developer, auditor sistem  
**Sumber konteks awal:** arsitektur existing pada `AGENTS.md` dan rancangan diagram pengguna.

---

## 1. Ringkasan Produk

Produk ini adalah chatbot internal berbasis RAG yang menjawab pertanyaan pengguna hanya berdasarkan dokumen yang telah diunggah dan diindeks ke knowledge base internal. Sistem harus mampu memproses dokumen PDF, DOCX, XLSX, dan CSV; mengubah isi dokumen menjadi chunk terstruktur; membuat embedding; menyimpan vector ke Qdrant; menyimpan metadata ke PostgreSQL; lalu melakukan retrieval, reranking, validasi keterjawaban, dan pembuatan jawaban dengan citation yang dapat diaudit.

Produk tidak boleh berfungsi sebagai chatbot umum. Jika informasi tidak tersedia dalam knowledge base internal, sistem harus menyatakan bahwa informasi tidak ditemukan, bukan membuat asumsi. Fallback Google Search hanya boleh digunakan sebagai opsi eksternal yang diberi label jelas dan tidak boleh dicampur dengan sumber internal.

Tujuan desain ini adalah menghasilkan chatbot yang:

1. akurat dan grounded pada dokumen internal;
2. meminimalkan halusinasi melalui retrieval, reranking, answerability gate, dan citation validator;
3. cepat melalui pipeline asinkron, caching, Qdrant gRPC, dan streaming;
4. aman melalui auth, RBAC, sanitasi input, validasi upload, audit log, dan proteksi prompt injection;
5. stabil melalui worker terpisah, retry, circuit breaker, health check, dan test gate;
6. mudah dievaluasi melalui logging, feedback, dan dataset pengujian RAG.

---

## 2. Latar Belakang

Organisasi membutuhkan chatbot internal yang dapat menjawab pertanyaan berdasarkan dokumen perusahaan, SOP, data tabular, dan dokumen operasional lain. Arsitektur existing telah memiliki FastAPI, React, Qdrant, PostgreSQL, Ollama embedding, Groq API, Google Custom Search fallback, endpoint chat, streaming, upload dokumen, feedback, rate limiter, structured extractor, dan citation insertion.

Masalah utama yang harus diselesaikan dalam PRD ini adalah:

1. ingestion pipeline dan query pipeline masih perlu dipisahkan secara tegas;
2. sistem harus memastikan jawaban hanya berasal dari dokumen internal;
3. citation harus benar-benar terhubung dengan chunk sumber, bukan sekadar semantic match setelah jawaban dibuat;
4. keamanan produksi belum cukup jika tidak ada auth dan RBAC;
5. auto-ingestion saat startup perlu diganti atau dilengkapi worker agar startup tidak lambat dan tidak rapuh;
6. embedding model perlu dibenchmark ulang, terutama untuk Bahasa Indonesia dan dokumen multilingual;
7. sistem perlu observability dan evaluation harness agar kualitas RAG dapat diukur secara objektif.

---

## 3. Sasaran Produk

### 3.1 Sasaran Fungsional

Sistem harus dapat:

1. menerima pertanyaan pengguna dalam Bahasa Indonesia;
2. menormalisasi, membersihkan, dan memahami query;
3. melakukan query rewrite berbasis riwayat percakapan;
4. melakukan synonym expansion domain-specific;
5. mengambil dokumen relevan dari Qdrant dan metadata dari PostgreSQL;
6. melakukan hybrid retrieval dense + sparse/keyword;
7. melakukan reranking untuk menyaring chunk relevan;
8. menentukan apakah evidence cukup untuk menjawab;
9. menghasilkan jawaban berbasis konteks internal dengan citation;
10. menolak pertanyaan di luar konteks secara sopan;
11. memproses dokumen upload secara asinkron;
12. menampilkan status ingestion dokumen;
13. menerima feedback thumbs up/down;
14. mencatat audit log untuk aktivitas penting;
15. menyediakan health check untuk dependency utama.

### 3.2 Sasaran Non-Fungsional

Sistem harus memenuhi target berikut:

| Area | Target |
|---|---|
| Akurasi | Jawaban harus berbasis chunk yang ditemukan dan tervalidasi. |
| Anti-halusinasi | Jika evidence tidak cukup, sistem wajib abstain. |
| Latency | p50 query sederhana < 2 detik; p95 query RAG < 8 detik pada environment target. |
| Security | Auth, RBAC, rate limit, audit log, secret env, validasi upload, CORS strict. |
| Reliability | Failure setiap dependency harus menghasilkan error terkontrol, bukan crash tanpa pesan. |
| Observability | Semua tahap pipeline harus memiliki structured log dan latency metric. |
| Maintainability | Menggunakan linter, formatter, typecheck, migration, test suite, dan CI. |
| Bahasa | UI, system prompt, fallback, dan pesan error user-facing menggunakan Bahasa Indonesia. |

---

## 4. Non-Goals

Fitur berikut tidak termasuk dalam scope versi ini:

1. chatbot umum yang menjawab dari pengetahuan bawaan model tanpa retrieval;
2. multi-agent autonomous workflow yang dapat mengubah data perusahaan tanpa approval;
3. fine-tuning LLM;
4. training embedding model sendiri;
5. integrasi SSO enterprise kompleks di luar basic auth/JWT/RBAC tahap awal;
6. integrasi ERP/CRM langsung kecuali melalui MCP/tool gateway yang disetujui;
7. web search otomatis tanpa izin eksplisit atau label sumber eksternal;
8. penggunaan data user untuk training model;
9. penghapusan audit log secara otomatis tanpa retention policy.

---

## 5. Pengguna dan Role

### 5.1 Viewer / Internal User

Hak akses:

1. mengirim pertanyaan ke chatbot;
2. melihat jawaban dan citation;
3. memberikan feedback;
4. melihat riwayat percakapan miliknya sendiri jika fitur history diaktifkan.

Tidak boleh:

1. upload dokumen;
2. menghapus dokumen;
3. melihat dokumen yang tidak memiliki permission;
4. mengakses audit log.

### 5.2 Admin Dokumen

Hak akses:

1. upload dokumen;
2. melihat daftar dokumen;
3. melihat status ingestion;
4. menghapus dokumen;
5. mengatur metadata dokumen;
6. melihat error ingestion.

Tidak boleh:

1. mengubah konfigurasi sistem sensitif;
2. melihat secret;
3. bypass RBAC.

### 5.3 System Admin

Hak akses:

1. semua hak Admin Dokumen;
2. mengatur konfigurasi sistem;
3. mengakses audit log;
4. mengelola user dan role;
5. menjalankan reindex;
6. melihat observability dashboard.

### 5.4 Auditor

Hak akses:

1. membaca audit log;
2. membaca feedback;
3. melihat metadata retrieval dan citation;
4. mengekspor laporan evaluasi.

Tidak boleh:

1. menghapus dokumen;
2. mengubah konfigurasi;
3. mengubah jawaban atau feedback.

---

## 6. Scope MVP Produksi

Scope MVP produksi mencakup:

1. backend FastAPI;
2. frontend React 18 + Vite;
3. PostgreSQL 16 untuk metadata, session, feedback, audit log;
4. Qdrant v1.12.1 untuk vector store;
5. embedding via Ollama, dengan benchmark untuk model multilingual;
6. Groq API sebagai LLM provider melalui abstraction layer;
7. worker ingestion terpisah;
8. Redis untuk cache dan queue jika dipilih;
9. auth dan RBAC minimum;
10. upload PDF, DOCX, XLSX, CSV maksimal 50 MB;
11. RAG query non-streaming dan streaming SSE;
12. fallback Google Custom Search sebagai opsi eksternal terkontrol;
13. feedback endpoint;
14. health, readiness, dan liveness endpoint;
15. evaluation harness untuk dataset pertanyaan-jawaban.

---

## 7. Arsitektur Target

### 7.1 Komponen Utama

1. **Frontend Web App**  
   React 18 + Vite untuk interface chat, upload dokumen, daftar dokumen, status ingestion, feedback, dan admin panel.

2. **API Gateway / Reverse Proxy**  
   Nginx/Caddy/Traefik untuk TLS termination, request limit, header security, dan routing.

3. **FastAPI Backend**  
   Menyediakan REST API, SSE streaming, auth, orchestration RAG, document management, dan feedback.

4. **RAG Orchestrator**  
   Mengatur query processing, retrieval, reranking, answerability gate, context building, LLM call, citation validation, dan response formatting.

5. **Embedding Service**  
   Menghasilkan embedding untuk query dan dokumen. Harus memiliki retry, timeout, cache, dan observability.

6. **Qdrant Vector Store**  
   Menyimpan vector chunk beserta payload metadata. Menggunakan cosine similarity dan gRPC jika tersedia.

7. **PostgreSQL Metadata Store**  
   Menyimpan user, role, session, chat history, document metadata, chunk metadata, ingestion job, feedback, dan audit log.

8. **Ingestion Worker**  
   Memproses dokumen upload secara asinkron: parse, clean, chunk, embed, upsert, dan update status.

9. **LLM Gateway**  
   Abstraction layer untuk Groq API agar provider dapat diganti tanpa mengubah pipeline utama.

10. **Fallback Search Service**  
   Google Custom Search JSON API sebagai sumber eksternal opsional. Wajib diberi label eksternal.

11. **Observability Stack**  
   Structured logs, metrics, tracing, dan dashboard.

12. **MCP / Tool Gateway Opsional**  
   Digunakan hanya jika sistem perlu mengakses tool eksternal secara standar. MCP tidak menggantikan RAG orchestrator.

---

## 8. Pipeline Ingestion Dokumen

### 8.1 Alur Standar

Admin upload dokumen → validasi file → simpan file original → buat ingestion job → worker memproses dokumen → parsing → cleaning → chunking → embedding batch → upsert ke Qdrant → simpan metadata chunk ke PostgreSQL → update status job.

### 8.2 Validasi File

Sistem harus memvalidasi:

1. ukuran file maksimal 50 MB;
2. ekstensi hanya PDF, DOCX, XLSX, CSV;
3. MIME type sesuai;
4. file signature sesuai;
5. filename disanitasi;
6. file kosong atau kurang dari threshold minimal ditolak;
7. Excel temporary file seperti `~$filename.xlsx` di-skip;
8. file dengan potensi malware ditolak jika antivirus scanner tersedia;
9. duplikasi dicek berdasarkan hash, bukan hanya filename.

### 8.3 Parsing

| Format | Parser | Ketentuan |
|---|---|---|
| PDF | parser PDF yang stabil | Simpan page number. Jika text extraction gagal, status partial/failed. OCR tidak wajib pada MVP. |
| DOCX | python-docx/unstructured | Pertahankan heading dan paragraph structure. |
| CSV | pandas | Deteksi encoding, delimiter, header. |
| XLSX | pandas/openpyxl | Skip sheet kosong, simpan nama sheet, row-aware formatting. |

### 8.4 Chunking

Chunking harus adaptif:

1. dokumen naratif: 400–800 token per chunk, overlap 50–100;
2. SOP: chunk berdasarkan heading/subheading jika tersedia;
3. tabel: row-aware chunking, satu row tidak boleh terpotong;
4. dokumen panjang: simpan page dan section;
5. chunk kosong tidak boleh diinsert;
6. setiap chunk wajib memiliki hash.

### 8.5 Metadata Chunk

Setiap chunk minimal memiliki payload:

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "file_name": "string",
  "source_type": "pdf|docx|xlsx|csv",
  "page_number": 1,
  "sheet_name": "string|null",
  "section_title": "string|null",
  "chunk_index": 0,
  "text": "string",
  "text_hash": "sha256",
  "document_hash": "sha256",
  "version": 1,
  "access_level": "internal|restricted|confidential",
  "created_at": "datetime"
}
```

### 8.6 Status Ingestion

Status yang wajib didukung:

1. `uploaded`;
2. `queued`;
3. `processing`;
4. `completed`;
5. `partial_failed`;
6. `failed`;
7. `deleted`.

Setiap error ingestion harus disimpan dengan error code dan human-readable message.

---

## 9. Pipeline Query RAG

### 9.1 Alur Standar

User question → auth/RBAC → rate limit → input sanitization → query normalization → intent classification → session/history loading → query rewrite → synonym expansion → query embedding → hybrid retrieval → metadata permission filter → reranking → context compression → answerability gate → LLM generation → citation validation → response formatting → save chat history → return answer.

### 9.2 Input Sanitization

Sistem harus:

1. menghapus zero-width unicode;
2. menormalisasi fullwidth ke halfwidth;
3. menghapus URL tracking yang tidak diperlukan;
4. membatasi panjang query;
5. menolak payload kosong;
6. menolak input yang mencoba eksploitasi format atau prompt injection secara eksplisit jika berbahaya;
7. menjaga karakter Bahasa Indonesia tetap valid.

### 9.3 Intent Classification

Minimal intent:

1. `casual_greeting`;
2. `rag_question`;
3. `tabular_lookup`;
4. `out_of_scope`;
5. `fallback_request`;
6. `document_management`;
7. `unsafe_or_policy_violation`.

Greeting boleh dijawab tanpa retrieval, tetapi hanya untuk sapaan sederhana. Pertanyaan substantif wajib melewati RAG pipeline.

### 9.4 Query Rewrite

Query rewrite harus:

1. menggunakan maksimal 10 turn terakhir;
2. tidak menambahkan fakta baru;
3. mengubah pertanyaan follow-up menjadi pertanyaan mandiri;
4. mempertahankan istilah domain;
5. menyimpan query asli dan query rewrite untuk audit.

### 9.5 Synonym Expansion

Synonym expansion harus:

1. memakai file domain seperti `backend/app/data/synonyms.json`;
2. tidak memperluas query secara agresif hingga mengubah maksud;
3. dapat dinonaktifkan melalui env var;
4. memiliki unit test.

### 9.6 Retrieval

Retrieval harus:

1. melakukan dense vector search;
2. mendukung sparse/keyword search untuk istilah spesifik;
3. menggabungkan hasil dengan Reciprocal Rank Fusion atau mekanisme fusion lain;
4. mengambil kandidat awal minimal top-20;
5. menerapkan permission filter berdasarkan role/user;
6. tidak mengembalikan chunk dari dokumen deleted atau failed;
7. menyimpan score untuk observability.

### 9.7 Reranking

Reranking harus:

1. menilai relevansi query terhadap chunk;
2. menyaring chunk yang tidak relevan;
3. menghasilkan rerank score;
4. membatasi jumlah context final berdasarkan token budget;
5. memiliki fallback jika reranker unavailable.

Reranker LLM boleh digunakan pada MVP, tetapi PRD ini merekomendasikan abstraction layer agar dapat diganti dengan cross-encoder reranker.

### 9.8 Answerability Gate

Sistem wajib mengecek apakah evidence cukup.

Contoh rule awal:

1. tidak ada chunk relevan → abstain;
2. top score di bawah threshold → abstain;
3. rerank score semua kandidat rendah → abstain;
4. pertanyaan meminta angka spesifik tetapi structured extractor gagal menemukan nilai → jawab bahwa data tidak ditemukan;
5. pertanyaan meminta kebijakan internal tetapi dokumen sumber tidak tersedia → abstain;
6. pertanyaan ambigu → minta klarifikasi.

Output abstain harus sopan dan jelas, misalnya:

> Saya belum menemukan informasi yang cukup dalam knowledge base internal untuk menjawab pertanyaan tersebut. Silakan unggah dokumen terkait atau perjelas pertanyaan.

### 9.9 Context Builder

Context untuk LLM harus:

1. berisi chunk bernomor;
2. mencantumkan metadata sumber;
3. dibatasi token budget;
4. menghilangkan duplikasi;
5. memprioritaskan chunk dengan rerank score tertinggi;
6. menyertakan `[FAKTA TERVERIFIKASI]` untuk data tabular yang diekstrak langsung;
7. tidak menyertakan dokumen yang user tidak berhak akses.

Format rekomendasi:

```text
[CHUNK C1]
File: SOP-Pengadaan.pdf
Halaman: 4
Section: Prosedur Persetujuan
Isi: ...

[CHUNK C2]
File: Kebijakan-HR.docx
Section: Cuti Tahunan
Isi: ...
```

### 9.10 LLM Generation

LLM harus diberi system prompt ketat:

```text
Anda adalah chatbot knowledge base internal. Jawab hanya berdasarkan CONTEXT yang diberikan. Jangan menggunakan pengetahuan eksternal. Jika informasi tidak tersedia dalam CONTEXT, katakan bahwa informasi tidak ditemukan dalam knowledge base internal. Jangan membuat asumsi. Setiap klaim penting harus memiliki citation berupa ID chunk yang tersedia. Gunakan Bahasa Indonesia yang jelas dan profesional.
```

Parameter awal:

1. temperature: 0.0–0.2 untuk jawaban faktual;
2. max_tokens: disesuaikan kebutuhan, default 1024;
3. timeout eksplisit;
4. retry terbatas;
5. fallback terkontrol jika provider gagal.

### 9.11 Citation Validation

Citation validator harus:

1. memastikan citation ID yang digunakan model berasal dari context yang diberikan;
2. menolak citation yang tidak valid;
3. memastikan minimal satu citation untuk jawaban faktual;
4. jika citation tidak valid, lakukan satu kali regeneration dengan instruksi koreksi;
5. jika tetap gagal, return error terkontrol atau jawaban abstain;
6. menyimpan citation mapping di database.

Citation tidak boleh dibuat hanya berdasarkan kemiripan semantic setelah jawaban selesai. Citation harus diikat pada chunk ID yang tersedia dalam context.

### 9.12 Response Format

Response JSON minimal:

```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "answer": "string",
  "citations": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "file_name": "string",
      "page_number": 1,
      "section_title": "string|null"
    }
  ],
  "confidence": "high|medium|low|abstain",
  "is_fallback": false,
  "latency_ms": 1234
}
```

---

## 10. Structured Data Handling

Untuk query yang meminta angka, tanggal, harga, nilai, status, jumlah, atau field spesifik dari CSV/XLSX, sistem tidak boleh hanya mengandalkan LLM.

Pipeline:

1. classify intent sebagai `tabular_lookup`;
2. identifikasi file kandidat;
3. baca file asli atau cache structured representation;
4. parse filter dari query;
5. cari nilai dengan pandas;
6. inject hasil sebagai `[FAKTA TERVERIFIKASI]`;
7. LLM hanya merapikan jawaban, bukan membuat angka.

Jika data tidak ditemukan, sistem harus mengatakan data tidak ditemukan.

---

## 11. Fallback Search Policy

Fallback Google Search hanya boleh digunakan dengan aturan berikut:

1. fallback tidak otomatis untuk pertanyaan internal sensitif;
2. fallback harus ditawarkan atau diminta eksplisit oleh user;
3. hasil fallback diberi label `Sumber eksternal`;
4. hasil fallback tidak boleh dicampur dengan citation internal;
5. fallback tidak boleh menyimpan data rahasia ke query eksternal;
6. query fallback harus disanitasi;
7. fallback event harus masuk audit log.

Contoh pesan:

> Informasi tersebut tidak ditemukan dalam knowledge base internal. Saya dapat mencarikan sumber eksternal jika Anda mengizinkan.

---

## 12. Security Requirements

### 12.1 Auth dan RBAC

Sistem produksi wajib memiliki auth.

Minimum:

1. JWT access token;
2. refresh token opsional;
3. password hashing `bcrypt` atau `argon2` jika local auth digunakan;
4. role: `viewer`, `document_admin`, `system_admin`, `auditor`;
5. endpoint admin wajib memeriksa role;
6. query retrieval wajib menerapkan document permission filter.

### 12.2 Secret Management

1. API key tidak boleh hardcoded;
2. secret disimpan di `.env` untuk local development;
3. production menggunakan secret manager atau environment secret;
4. `.env` wajib masuk `.gitignore`;
5. log tidak boleh mencetak secret.

### 12.3 Upload Security

1. validasi ekstensi, MIME, dan signature;
2. filename sanitized;
3. simpan file dengan UUID, bukan nama asli sebagai path utama;
4. path traversal wajib dicegah;
5. limit ukuran file;
6. scan malware jika scanner tersedia;
7. jangan render raw HTML dari dokumen.

### 12.4 Prompt Injection Defense

Sistem harus:

1. memisahkan instruksi sistem dari isi dokumen;
2. menandai dokumen sebagai untrusted content;
3. menolak instruksi dalam dokumen yang meminta model mengabaikan sistem;
4. melakukan sanitasi input user;
5. membatasi tool yang dapat dipanggil model;
6. tidak membiarkan LLM memilih sendiri permission;
7. menyimpan prompt injection detection flag untuk audit.

### 12.5 Rate Limiting

1. chat endpoint dibatasi per user dan per IP;
2. admin endpoint memiliki limit lebih ketat;
3. upload endpoint memiliki limit ukuran dan frekuensi;
4. 429 response harus jelas;
5. stale limiter state dibersihkan periodik.

### 12.6 Audit Log

Audit log wajib mencatat:

1. login/logout;
2. upload dokumen;
3. delete dokumen;
4. ingestion failed;
5. query RAG;
6. fallback external search;
7. feedback;
8. permission denied;
9. config change.

Audit log minimal berisi:

```json
{
  "event_id": "uuid",
  "actor_user_id": "uuid|null",
  "event_type": "string",
  "resource_type": "string",
  "resource_id": "uuid|null",
  "ip_address": "string",
  "user_agent": "string",
  "metadata": {},
  "created_at": "datetime"
}
```

---

## 13. Reliability Requirements

Sistem harus menangani dependency failure secara terkontrol.

| Failure | Respons Sistem |
|---|---|
| PostgreSQL down | `/ready` gagal, API yang butuh DB return 503. |
| Qdrant down | Query RAG return 503 terkontrol, tidak fallback ke jawaban LLM bebas. |
| Ollama down | Embedding gagal dengan retry, lalu return error terkontrol. |
| Groq API down | Retry terbatas, lalu return error terkontrol. |
| Worker down | Upload tetap diterima jika queue tersedia, status tetap `queued`; admin melihat warning. |
| Parsing gagal | Ingestion job `failed` atau `partial_failed`. |
| Citation invalid | Regenerate sekali, lalu abstain/error terkontrol. |
| Session expired | Buat session baru dan return `session_id` baru, client wajib update. |

Tambahkan:

1. timeout eksplisit untuk semua external call;
2. retry dengan exponential backoff;
3. circuit breaker untuk LLM dan embedding;
4. idempotent ingestion berdasarkan document hash;
5. dead-letter queue untuk job gagal;
6. readiness dan liveness endpoint.

---

## 14. Performance Requirements

### 14.1 Target Latency

| Operasi | Target |
|---|---|
| Chat non-RAG greeting | p95 < 1 detik |
| Chat RAG normal | p50 < 2 detik, p95 < 8 detik |
| Streaming first token | p95 < 3 detik |
| Upload response | < 2 detik untuk menerima file dan membuat job |
| Ingestion dokumen kecil | selesai < 60 detik, tergantung ukuran dan parser |
| List documents | p95 < 1 detik |

### 14.2 Optimasi

1. gunakan Qdrant gRPC jika tersedia;
2. cache query embedding;
3. cache retrieval untuk query identik dengan document index version sama;
4. batch embedding saat ingestion;
5. batasi context token;
6. gunakan streaming SSE;
7. gunakan connection pooling sesuai observasi;
8. jangan jalankan ingestion berat pada startup API.

---

## 15. Observability Requirements

Sistem wajib menyimpan structured log per request.

Metric minimal:

1. total request count;
2. error rate;
3. p50/p95 latency;
4. retrieval latency;
5. rerank latency;
6. LLM latency;
7. embedding latency;
8. ingestion success/failure rate;
9. fallback rate;
10. abstain rate;
11. feedback positive/negative rate;
12. citation validation failure rate;
13. token usage;
14. Qdrant health;
15. PostgreSQL health.

Log query harus meminimalkan exposure data sensitif. Email, phone, token, dan secret harus dimasking.

---

## 16. Database Design

### 16.1 PostgreSQL Tables

#### `users`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | User ID |
| email | VARCHAR unique | Login identity |
| name | VARCHAR | Display name |
| password_hash | VARCHAR nullable | Jika local auth dipakai |
| is_active | BOOLEAN | Default true |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `roles`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR unique | viewer/document_admin/system_admin/auditor |
| description | TEXT | |

#### `user_roles`

| Column | Type | Notes |
|---|---|---|
| user_id | UUID FK | |
| role_id | UUID FK | |

#### `documents`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| original_filename | TEXT | Sanitized display name |
| stored_filename | TEXT | UUID-based file path name |
| file_path | TEXT | Internal path |
| file_type | VARCHAR | pdf/docx/xlsx/csv |
| mime_type | VARCHAR | |
| size_bytes | BIGINT | |
| document_hash | VARCHAR | SHA256 |
| access_level | VARCHAR | internal/restricted/confidential |
| status | VARCHAR | uploaded/queued/processing/completed/partial_failed/failed/deleted |
| version | INT | |
| uploaded_by | UUID FK | |
| error_code | VARCHAR nullable | |
| error_message | TEXT nullable | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `document_chunks`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | chunk_id |
| document_id | UUID FK | |
| chunk_index | INT | |
| text_hash | VARCHAR | SHA256 |
| page_number | INT nullable | |
| sheet_name | TEXT nullable | |
| section_title | TEXT nullable | |
| token_count | INT | |
| qdrant_point_id | UUID | |
| created_at | TIMESTAMP | |

#### `ingestion_jobs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | UUID FK | |
| status | VARCHAR | queued/processing/completed/failed |
| attempts | INT | |
| max_attempts | INT | |
| error_code | VARCHAR nullable | |
| error_message | TEXT nullable | |
| started_at | TIMESTAMP nullable | |
| finished_at | TIMESTAMP nullable | |
| created_at | TIMESTAMP | |

#### `chat_sessions`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID nullable | nullable untuk MVP jika anonymous masih dipertahankan |
| expires_at | TIMESTAMP | default 30 menit |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### `chat_messages`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK | |
| user_id | UUID nullable | |
| role | VARCHAR | user/assistant/system |
| content | TEXT | |
| query_original | TEXT nullable | |
| query_rewritten | TEXT nullable | |
| confidence | VARCHAR nullable | high/medium/low/abstain |
| latency_ms | INT nullable | |
| token_usage | JSONB nullable | |
| created_at | TIMESTAMP | |

#### `message_citations`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK | assistant message |
| chunk_id | UUID FK | |
| document_id | UUID FK | |
| quote_start | INT nullable | optional |
| quote_end | INT nullable | optional |
| created_at | TIMESTAMP | |

#### `feedback`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK | |
| user_id | UUID nullable | |
| feedback | VARCHAR | positive/negative |
| comment | TEXT nullable | |
| created_at | TIMESTAMP | |

#### `audit_logs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| actor_user_id | UUID nullable | |
| event_type | VARCHAR | |
| resource_type | VARCHAR | |
| resource_id | UUID nullable | |
| ip_address | VARCHAR nullable | |
| user_agent | TEXT nullable | |
| metadata | JSONB | |
| created_at | TIMESTAMP | |

#### `rag_evaluation_cases`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| question | TEXT | |
| expected_answer | TEXT nullable | |
| expected_document_ids | UUID[] nullable | |
| expected_chunk_ids | UUID[] nullable | |
| category | VARCHAR | |
| created_at | TIMESTAMP | |

#### `rag_evaluation_runs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| case_id | UUID FK | |
| answer | TEXT | |
| retrieved_chunk_ids | UUID[] | |
| metrics | JSONB | |
| created_at | TIMESTAMP | |

---

## 17. Qdrant Collection Design

Collection default:

```text
company_knowledge_base
```

Vector config awal:

```json
{
  "size": 768,
  "distance": "Cosine"
}
```

Jika embedding model diganti dan dimensi berubah, wajib membuat collection baru dan migration/reindex. Jangan mengubah dimensi collection existing secara diam-diam.

Payload index yang direkomendasikan:

1. `document_id`;
2. `file_name`;
3. `source_type`;
4. `page_number`;
5. `section_title`;
6. `access_level`;
7. `document_hash`;
8. `version`;
9. `status`.

---

## 18. API Requirements

### 18.1 Chat

#### `POST /api/v1/chat/query`

Request:

```json
{
  "message": "string",
  "session_id": "uuid|null"
}
```

Response:

```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "answer": "string",
  "citations": [],
  "confidence": "high|medium|low|abstain",
  "is_fallback": false,
  "latency_ms": 1234
}
```

#### `POST /api/v1/chat/stream`

SSE events:

1. `metadata`;
2. `token`;
3. `citation`;
4. `fallback_offer`;
5. `done`;
6. `error`.

#### `POST /api/v1/chat/fallback`

Fallback hanya untuk sumber eksternal dan wajib memberi label external.

#### `POST /api/v1/chat/feedback`

Request:

```json
{
  "message_id": "uuid",
  "feedback": "positive|negative",
  "comment": "string|null"
}
```

### 18.2 Documents

#### `POST /api/v1/documents/upload`

Multipart upload. Response 202:

```json
{
  "document_id": "uuid",
  "job_id": "uuid",
  "status": "queued"
}
```

#### `GET /api/v1/documents`

Query params:

1. `page` default 1;
2. `per_page` default 50, max 200;
3. `status` optional;
4. `file_type` optional;
5. `q` optional.

#### `GET /api/v1/documents/{document_id}`

Return metadata dan ingestion status.

#### `DELETE /api/v1/documents/{document_id}`

Soft delete metadata dan delete vector terkait dari Qdrant.

### 18.3 Health

#### `GET /health`

Basic health.

#### `GET /ready`

Cek PostgreSQL, Qdrant, dan dependency wajib.

#### `GET /live`

Liveness process.

### 18.4 Admin Evaluation

#### `POST /api/v1/admin/evaluations/run`

Menjalankan evaluation set.

#### `GET /api/v1/admin/evaluations/{run_id}`

Melihat hasil evaluation.

---

## 19. Frontend Requirements

Frontend minimal memiliki halaman:

1. login;
2. chat;
3. daftar dokumen;
4. upload dokumen;
5. status ingestion;
6. detail dokumen;
7. feedback pada jawaban;
8. admin audit log untuk role auditor/system_admin;
9. evaluation dashboard untuk role system_admin.

UI chat harus menampilkan:

1. jawaban;
2. citation dengan nama file, halaman/sheet/section;
3. confidence label;
4. pesan abstain;
5. fallback offer;
6. loading state;
7. streaming state;
8. error state yang jelas.

---

## 20. Acceptance Criteria

### 20.1 Anti-Hallucination

1. Jika pertanyaan tidak memiliki chunk relevan, sistem menjawab abstain.
2. Jika LLM menghasilkan citation yang tidak ada di context, citation validator menolak output.
3. Jika user meminta jawaban di luar dokumen internal, sistem tidak menjawab dari pengetahuan umum.
4. Jawaban faktual memiliki minimal satu citation valid.
5. Query angka dari tabel menggunakan structured extractor jika data tersedia.

### 20.2 Security

1. Endpoint admin tidak bisa diakses oleh viewer.
2. Secret tidak muncul di repository dan log.
3. Upload file `.exe`, file kosong, file >50 MB, dan path traversal ditolak.
4. Rate limit mengembalikan 429.
5. Audit log tercatat untuk upload, delete, query, fallback, dan permission denied.

### 20.3 Reliability

1. Jika Qdrant mati, sistem tidak memanggil LLM untuk menjawab bebas.
2. Jika Ollama mati, sistem retry lalu return error terkontrol.
3. Jika Groq gagal, sistem retry lalu return error terkontrol.
4. Ingestion gagal tidak membuat API server crash.
5. Delete dokumen menghapus metadata aktif dan vector terkait.

### 20.4 Performance

1. Query greeting p95 < 1 detik.
2. Query RAG p95 < 8 detik pada dataset uji.
3. Upload response < 2 detik untuk dokumen standar.
4. List documents p95 < 1 detik.

### 20.5 Developer Quality

1. Semua test wajib pass.
2. Linter dan formatter pass.
3. Typecheck pass atau seluruh exception terdokumentasi.
4. Alembic migration berjalan dari database kosong.
5. Docker Compose dapat menjalankan stack lokal.

---

## 21. Evaluation Plan

Buat dataset evaluasi minimal 100 pertanyaan:

1. 40 pertanyaan faktual dokumen naratif;
2. 20 pertanyaan SOP/prosedur;
3. 20 pertanyaan tabular CSV/XLSX;
4. 10 pertanyaan out-of-scope;
5. 10 pertanyaan adversarial/prompt injection.

Metric:

1. Recall@5;
2. Recall@10;
3. MRR;
4. nDCG;
5. answer correctness;
6. faithfulness;
7. citation accuracy;
8. abstain accuracy;
9. latency p50/p95;
10. fallback rate.

Release tidak boleh dilakukan jika:

1. citation accuracy < 95%;
2. out-of-scope abstain accuracy < 95%;
3. prompt injection pass rate < 95%;
4. p95 latency > target tanpa justifikasi.

---

## 22. Environment Variables

Minimal:

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg2://user:pass@db:5432/app
QDRANT_URL=http://qdrant:6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION=company_knowledge_base
OLLAMA_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
GROQ_API_KEY=
GROQ_MODEL=
GOOGLE_API_KEY=
GOOGLE_CSE_ID=
JWT_SECRET_KEY=
RATE_LIMIT_WINDOW=60
RATE_LIMIT_CHAT_MAX=30
RATE_LIMIT_ADMIN_MAX=15
CHUNK_SIZE=512
CHUNK_OVERLAP=50
SIMILARITY_THRESHOLD=0.55
HYBRID_TOP_K=20
SESSION_TTL_MINUTES=30
SESSION_MAX_TURNS=10
UPLOAD_MAX_MB=50
ENABLE_EXTERNAL_FALLBACK=false
```

---

## 23. Deployment Requirements

1. Docker Compose untuk local development;
2. production dapat memakai VM, Docker Swarm, Kubernetes, atau managed container;
3. volume persistent untuk PostgreSQL, Qdrant, uploaded files/object storage;
4. backup PostgreSQL terjadwal;
5. snapshot Qdrant atau reindex plan;
6. TLS aktif di production;
7. CORS hanya domain frontend resmi;
8. log rotation aktif;
9. health check digunakan oleh orchestrator;
10. rollback plan tersedia.

---

## 24. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Retrieval lemah | Jawaban salah atau abstain berlebihan | Hybrid search, reranker, evaluation dataset. |
| Citation palsu | User percaya sumber yang salah | Citation validator berbasis chunk ID. |
| Prompt injection | Model mengikuti instruksi berbahaya | Sanitasi, prompt hardening, document-as-data policy. |
| Data leakage | Dokumen rahasia terlihat user salah | RBAC dan permission filter sebelum retrieval. |
| Startup lambat | Aplikasi tidak siap | Worker ingestion terpisah. |
| Embedding tidak cocok BI | Recall rendah | Benchmark multilingual embedding. |
| LLM provider down | Chat gagal | Retry, circuit breaker, fallback error terkontrol. |
| Google fallback bocor data | Data internal keluar | Fallback opt-in dan query sanitization. |

---

## 25. Milestones

### Milestone 0 — Baseline Audit

Audit repo existing, dependency, endpoint, pipeline, bug, dan test coverage.

### Milestone 1 — Architecture Hardening

Pisahkan ingestion worker, RAG orchestrator, LLM gateway, embedding service, dan repository layer.

### Milestone 2 — Security Foundation

Auth, RBAC, permission filter, upload validation, audit log, CORS, secret hygiene.

### Milestone 3 — RAG Quality

Hybrid retrieval, reranking, answerability gate, citation validator, structured extractor hardening.

### Milestone 4 — Observability and Evaluation

Structured logs, metrics, evaluation dataset, evaluation runner, feedback analytics.

### Milestone 5 — Production Readiness

CI/CD, Docker hardening, load test, backup/restore, deployment docs, release checklist.

---

## 26. Definition of Done Produk

Produk dianggap selesai untuk MVP produksi jika:

1. semua endpoint utama berjalan;
2. ingestion dokumen bekerja asinkron;
3. query RAG menjawab dengan citation valid;
4. out-of-scope ditolak;
5. auth dan RBAC aktif;
6. upload file aman;
7. audit log tercatat;
8. evaluation dataset dapat dijalankan;
9. CI test pass;
10. Docker Compose lokal berjalan dari fresh clone;
11. dokumentasi setup lengkap;
12. tidak ada secret hardcoded;
13. failure dependency menghasilkan error terkontrol.
