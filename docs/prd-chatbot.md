# Product Requirements Document (PRD)
# Internal Knowledge Base Chatbot

---

| Field        | Detail                                  |
|--------------|-----------------------------------------|
| **Product**  | Internal Knowledge Base Chatbot         |
| **Versi**    | 1.0.0 — MVP                             |
| **Tanggal**  | 2026-06-03                              |
| **Status**   | Draft — Pending Engineering Review      |
| **Author**   | Product & BA Team                       |
| **Audience** | Engineering, QA, Stakeholder Internal   |

---

## 1. Executive Summary

Perusahaan membutuhkan sebuah sistem chatbot internal berbasis AI yang memungkinkan karyawan mengakses informasi dari knowledge base perusahaan secara cepat, akurat, dan aman melalui antarmuka percakapan (conversational interface). Sistem ini dibangun di atas **RAG (Retrieval-Augmented Generation) Pipeline** dengan **Vector Database** sebagai mesin pencarian semantik, dan menggunakan **Groq API** (model open-source seperti LLaMA/Mixtral) sebagai LLM inferensi untuk MVP.

Chatbot dirancang dengan dua lapisan keandalan: jawaban utama diambil dari dokumen resmi internal perusahaan, dan apabila informasi tidak tersedia, sistem secara transparan menawarkan pencarian ke sumber eksternal (Google Search Fallback). Seluruh respons chatbot dibatasi ketat pada konteks bisnis yang telah ditetapkan — pertanyaan di luar scope akan di-reject secara elegan. Fase MVP berfokus pada platform Web App; integrasi Mobile App dan REST API dijadwalkan di fase berikutnya.

---

## 2. Problem Statement

Karyawan internal perusahaan kesulitan menemukan informasi yang relevan dari dokumen-dokumen perusahaan yang tersebar dalam berbagai format (PDF, DOCX, Excel/CSV) dan tidak terorganisir dalam satu sistem yang mudah diakses. Proses pencarian manual memakan waktu yang signifikan, mengurangi produktivitas, dan berpotensi menghasilkan pengambilan keputusan berbasis informasi yang sudah usang atau tidak lengkap.

Di sisi lain, solusi chatbot generik berbasis LLM berisiko memberikan jawaban di luar konteks bisnis, mengekspos data sensitif perusahaan, atau menghasilkan informasi yang tidak dapat diverifikasi (*hallucination*). Dibutuhkan sebuah sistem yang **terkurasi, terpercaya, dan terbatas pada konteks bisnis yang ditentukan**.

---

## 3. Goals & Non-Goals

### ✅ Goals (In-Scope MVP)

- Membangun RAG pipeline end-to-end yang mengindeks dokumen perusahaan (PDF, DOCX, Excel/CSV) ke dalam Vector Database.
- Menyediakan antarmuka chat berbasis Web App yang dapat diakses oleh 500–2.000 karyawan internal.
- Mengimplementasikan Google Search Fallback dengan mekanisme semi-manual (user dinotifikasi dan memilih untuk mencari ke sumber eksternal).
- Membangun Admin Panel (no-code UI) untuk upload dan manajemen dokumen knowledge base.
- Mengimplementasikan guardrails berbasis konteks bisnis — chatbot menolak dan memberi respons yang jelas untuk pertanyaan di luar scope yang ditetapkan.
- Memastikan data dokumen perusahaan tidak dikirimkan ke pihak ketiga selain LLM API yang digunakan.

### ❌ Non-Goals (Out-of-Scope MVP)

- Autentikasi dan otorisasi pengguna (SSO, OAuth) — dijadwalkan di fase Production.
- Integrasi Mobile App (iOS/Android) — dijadwalkan di Fase 2.
- REST API publik untuk integrasi sistem lain — dijadwalkan di Fase 2.
- Auto-sync dari sumber dokumen eksternal (Google Drive, SharePoint, Confluence) — dijadwalkan di Fase 3.
- Migrasi ke self-hosted LLM — dijadwalkan setelah MVP stable.
- Multi-language support (selain Bahasa yang ditetapkan).
- Analitik lanjutan berbasis user-level (membutuhkan autentikasi).

---

## 4. User Personas & Use Cases

### 4.1 User Personas

#### Persona 1 — Karyawan Internal (End User)
| Atribut     | Detail                                                              |
|-------------|---------------------------------------------------------------------|
| **Role**    | Karyawan di berbagai departemen (HR, Finance, Operations, dll.)     |
| **Goal**    | Menemukan informasi kebijakan, SOP, atau data perusahaan dengan cepat |
| **Pain Point** | Harus mencari manual di folder bersama atau bertanya ke rekan kerja |
| **Tech Savviness** | Low to Medium                                              |

#### Persona 2 — Knowledge Manager / Admin
| Atribut     | Detail                                                              |
|-------------|---------------------------------------------------------------------|
| **Role**    | IT Admin atau tim Knowledge Management                              |
| **Goal**    | Mengelola, memperbarui, dan mengontrol kualitas dokumen di knowledge base |
| **Pain Point** | Tidak ada sistem terpusat untuk mengontrol dokumen mana yang bisa diakses chatbot |
| **Tech Savviness** | Medium to High                                             |

---

### 4.2 Use Cases

| ID    | Use Case                              | Actor          | Deskripsi                                                                                   |
|-------|---------------------------------------|----------------|---------------------------------------------------------------------------------------------|
| UC-01 | Tanya Jawab dari Knowledge Base       | Karyawan       | User mengajukan pertanyaan, sistem melakukan semantic search ke Vector DB dan merespons berdasarkan dokumen internal. |
| UC-02 | Google Search Fallback                | Karyawan       | Sistem mendeteksi confidence score rendah, memberi notifikasi ke user, user memilih mencari ke Google, sistem menyajikan hasil. |
| UC-03 | Penolakan Pertanyaan Out-of-Context   | Karyawan       | User mengajukan pertanyaan di luar konteks bisnis, sistem menolak dengan pesan yang sopan dan informatif. |
| UC-04 | Upload Dokumen Baru                   | Admin          | Admin mengakses panel, mengupload file (PDF/DOCX/CSV), sistem memproses ingestion dan indexing ke Vector DB. |
| UC-05 | Manajemen Dokumen (Edit/Delete)       | Admin          | Admin dapat melihat daftar dokumen yang telah diindeks, menghapus, atau me-replace dokumen yang sudah tidak relevan. |
| UC-06 | Riwayat Percakapan (Session-based)   | Karyawan       | Sistem menyimpan konteks percakapan dalam satu sesi sehingga user dapat melakukan follow-up question. |

---

## 5. Functional Requirements

### 5.1 Module: RAG Chat Engine

#### FR-01 — Semantic Search via Vector DB
**Deskripsi:** Sistem harus mengubah query user menjadi embedding vector dan melakukan similarity search terhadap Vector Database untuk mengambil *top-k* chunk dokumen yang paling relevan.

**Acceptance Criteria:**
- [ ] Query user dikonversi ke embedding menggunakan model yang konsisten dengan model yang digunakan saat indexing.
- [ ] Sistem mengembalikan minimum 3 dan maksimum 5 chunk paling relevan (top-k configurable).
- [ ] Similarity score threshold dapat dikonfigurasi (default: ≥ 0.75) untuk menentukan relevansi.
- [ ] Jika tidak ada chunk dengan score ≥ threshold, sistem memicu alur fallback (FR-03).

---

#### FR-02 — Respons Generasi via Groq API
**Deskripsi:** Sistem harus menggabungkan chunk dokumen relevan sebagai context dan mengirimkannya bersama query user ke Groq API untuk menghasilkan respons.

**Acceptance Criteria:**
- [ ] Prompt ke LLM wajib menyertakan: system prompt (guardrails konteks bisnis) + retrieved context + conversation history + query user.
- [ ] Respons yang dihasilkan harus menyertakan referensi/sitasi sumber dokumen (nama file, halaman/baris jika tersedia).
- [ ] Response time end-to-end (query → tampil di UI) ≤ 5 detik dalam kondisi normal load.
- [ ] Jika Groq API tidak tersedia (timeout/error), sistem menampilkan pesan error yang informatif tanpa mengekspos detail teknis ke user.

---

#### FR-03 — Google Search Fallback (Semi-Manual)
**Deskripsi:** Ketika similarity score semua chunk berada di bawah threshold, sistem secara transparan memberi tahu user dan menawarkan opsi pencarian ke Google.

**Acceptance Criteria:**
- [ ] Sistem menampilkan pesan standar: *"Informasi ini tidak ditemukan dalam knowledge base perusahaan. Apakah kamu ingin saya carikan dari sumber eksternal?"* dengan tombol konfirmasi Ya/Tidak.
- [ ] Jika user memilih "Ya", sistem melakukan query ke Google Search API (Custom Search JSON API) dan menampilkan ringkasan hasil beserta URL sumber.
- [ ] Hasil dari Google Fallback diberi label visual yang jelas (misalnya badge *"Sumber Eksternal"*) untuk membedakannya dari jawaban berbasis KB internal.
- [ ] Jika user memilih "Tidak", percakapan berhenti pada notifikasi tersebut tanpa respons tambahan.

---

#### FR-04 — Guardrails & Context Boundary
**Deskripsi:** Sistem harus memiliki mekanisme untuk menolak pertanyaan yang berada di luar konteks bisnis yang telah ditetapkan dalam system prompt.

**Acceptance Criteria:**
- [ ] System prompt menyertakan definisi eksplisit tentang domain/konteks bisnis yang diizinkan.
- [ ] Chatbot menolak pertanyaan di luar konteks dengan pesan yang sopan, misalnya: *"Maaf, saya hanya dapat membantu pertanyaan yang berkaitan dengan [konteks bisnis]. Silakan ajukan pertanyaan yang relevan."*
- [ ] Penolakan tidak mengekspos isi system prompt ke user.
- [ ] Percakapan yang ditolak tetap tercatat di log sistem untuk keperluan audit dan evaluasi.

---

#### FR-05 — Conversation History (Session-Based)
**Deskripsi:** Sistem harus mempertahankan konteks percakapan dalam satu sesi aktif untuk mendukung follow-up question.

**Acceptance Criteria:**
- [ ] Sistem menyimpan minimal 10 turn terakhir (pasang user-assistant message) dalam satu sesi.
- [ ] Konteks sesi dikirimkan ke LLM pada setiap request untuk memungkinkan pertanyaan lanjutan yang koheren.
- [ ] Sesi berakhir otomatis setelah user tidak aktif selama 30 menit (configurable).
- [ ] User dapat mereset percakapan (tombol "New Chat") untuk memulai sesi baru.

---

### 5.2 Module: Document Ingestion & Admin Panel

#### FR-06 — Document Upload via Admin UI
**Deskripsi:** Admin harus dapat mengupload dokumen melalui antarmuka web tanpa memerlukan akses teknis.

**Acceptance Criteria:**
- [ ] Admin Panel mendukung upload file dengan format: `.pdf`, `.docx`, `.xlsx`, `.csv`.
- [ ] Batas ukuran file per upload: maksimum 50 MB per file (configurable).
- [ ] Sistem menampilkan progress bar saat proses upload berlangsung.
- [ ] Setelah upload, sistem secara otomatis memulai proses ingestion pipeline (chunking → embedding → indexing ke Vector DB).
- [ ] Admin menerima notifikasi (in-app atau email) ketika dokumen berhasil atau gagal diindeks.

---

#### FR-07 — Document Processing Pipeline
**Deskripsi:** Sistem harus memproses dokumen yang diupload menjadi vector embeddings yang dapat di-query.

**Acceptance Criteria:**
- [ ] PDF: diekstrak teks menggunakan parser (seperti PyMuPDF / pdfplumber); mendukung PDF berbasis teks maupun scanned (dengan OCR fallback).
- [ ] DOCX: diekstrak teks beserta struktur heading untuk mempertahankan hierarki informasi.
- [ ] Excel/CSV: setiap baris diperlakukan sebagai unit semantik; header kolom diikutsertakan dalam konteks setiap chunk.
- [ ] Teks dipotong ke dalam chunk dengan ukuran 512 token dengan overlap 50 token (configurable).
- [ ] Setiap chunk menyimpan metadata: nama file, halaman/baris asal, tanggal upload, versi dokumen.

---

#### FR-08 — Document Management (List, Update, Delete)
**Deskripsi:** Admin harus dapat melihat, memperbarui, dan menghapus dokumen dari knowledge base.

**Acceptance Criteria:**
- [ ] Admin Panel menampilkan daftar semua dokumen yang telah diindeks beserta metadata (nama, ukuran, tanggal upload, status indexing).
- [ ] Admin dapat menghapus dokumen; penghapusan harus menghapus seluruh vector embedding terkait dari Vector DB.
- [ ] Admin dapat me-replace dokumen (upload versi baru); sistem secara otomatis menghapus embedding versi lama dan membuat yang baru.
- [ ] Tersedia fitur pencarian/filter dokumen berdasarkan nama file atau tanggal upload.

---

## 6. Non-Functional Requirements

### 6.1 Performance

| ID      | Requirement                                                                  | Target           |
|---------|------------------------------------------------------------------------------|------------------|
| NFR-01  | Response time end-to-end (query hingga respons tampil)                       | ≤ 5 detik (P95)  |
| NFR-02  | Document ingestion time per dokumen (≤ 10MB)                                 | ≤ 60 detik       |
| NFR-03  | Concurrent active users yang dapat dilayani tanpa degradasi performa         | ≥ 200 concurrent |
| NFR-04  | Vector DB similarity search latency                                          | ≤ 300 ms (P99)   |
| NFR-05  | Availability / Uptime sistem                                                 | ≥ 99.5% (monthly)|

---

### 6.2 Scalability

- Arsitektur backend harus stateless dan dapat di-scale secara horizontal (containerized, mendukung deployment di Kubernetes atau Docker Compose untuk MVP).
- Vector DB harus mampu menangani pertumbuhan hingga **1 juta vector** tanpa perubahan arsitektur signifikan.
- LLM layer (Groq API) harus dapat diganti dengan self-hosted model di masa mendatang melalui abstraksi interface (LLM Provider abstraction layer).

---

### 6.3 Security

| ID      | Requirement                                                                                           |
|---------|-------------------------------------------------------------------------------------------------------|
| SEC-01  | Seluruh komunikasi antar layanan menggunakan HTTPS / TLS 1.2+.                                        |
| SEC-02  | API Key Groq dan Google Custom Search API disimpan di environment variable atau secret manager (bukan hardcoded). |
| SEC-03  | Dokumen perusahaan yang diupload **tidak disimpan secara permanen** di storage pihak ketiga selain infrastructure yang digunakan. |
| SEC-04  | Data chunk dokumen yang dikirim ke Groq API hanya berupa potongan teks konteks yang relevan, bukan seluruh dokumen. |
| SEC-05  | Admin Panel wajib diakses melalui jaringan internal atau VPN perusahaan (network-level access control). |
| SEC-06  | Semua aktivitas admin (upload, delete, replace dokumen) dicatat dalam audit log.                      |
| SEC-07  | Input user disanitasi sebelum dimasukkan ke dalam prompt untuk mencegah prompt injection.             |

*Catatan: Autentikasi user (SSO/OAuth) di-defer ke fase Production.*

---

### 6.4 Maintainability & Observability

- Sistem harus menyediakan logging terstruktur (JSON format) untuk setiap request/response cycle.
- Tersedia dashboard monitoring dasar (uptime, error rate, average response time) — dapat menggunakan tools seperti Grafana + Prometheus atau solusi managed.
- Konfigurasi kritis (confidence threshold, max chunk, LLM model name, session timeout) harus dapat diubah via environment variable tanpa perlu rebuild container.

---

## 7. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        WEB APP (Frontend)                        │
│              Chat Interface │ Admin Panel (Upload UI)            │
└─────────────────┬───────────────────────────┬───────────────────┘
                  │ User Query                │ Document Upload
                  ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND API SERVICE                         │
│                    (REST API / FastAPI)                          │
│                                                                  │
│  ┌──────────────────┐        ┌────────────────────────────────┐  │
│  │  RAG Pipeline    │        │  Document Ingestion Pipeline   │  │
│  │                  │        │                                │  │
│  │ 1. Embed Query   │        │ 1. Parse (PDF/DOCX/CSV)        │  │
│  │ 2. Vector Search │        │ 2. Chunking (512 token)        │  │
│  │ 3. Build Prompt  │        │ 3. Embedding Generation        │  │
│  │ 4. Call LLM API  │        │ 4. Upsert to Vector DB         │  │
│  └────────┬─────────┘        └──────────────┬─────────────────┘  │
│           │                                 │                    │
└───────────┼─────────────────────────────────┼────────────────────┘
            │                                 │
     ┌──────▼──────┐                   ┌──────▼──────┐
     │  Vector DB  │                   │  File Store │
     │ (Qdrant /   │                   │  (Temp /    │
     │  Weaviate / │                   │   Local FS) │
     │  Pinecone)  │                   └─────────────┘
     └──────┬──────┘
            │ Top-K Chunks
            ▼
     ┌─────────────┐        Confidence < Threshold
     │  LLM Layer  │ ──────────────────────────────►  Google Search API
     │ (Groq API)  │                                  (Custom Search JSON)
     └──────┬──────┘
            │ Generated Response
            ▼
     ┌─────────────┐
     │ Guardrails  │ ── Out-of-context? → Reject with message
     │  Validator  │ ── In-context? → Return response to user
     └─────────────┘
```

### Alur Kerja Utama (RAG Flow)

1. **User mengirim query** melalui Web App.
2. **Backend** menerima query, melakukan **sanitasi input** (mencegah prompt injection).
3. Query dikonversi menjadi **embedding vector** menggunakan embedding model.
4. **Vector DB** mengembalikan top-k chunk dengan similarity score tertinggi.
5. **Guardrail check pertama:** apakah query termasuk dalam konteks bisnis yang diizinkan?
   - Jika **TIDAK** → kembalikan pesan penolakan standar.
6. **Confidence check:** apakah similarity score tertinggi ≥ threshold?
   - Jika **TIDAK** → tampilkan notifikasi fallback ke user, tunggu konfirmasi.
   - Jika user konfirmasi "Ya" → query ke **Google Search API**, tampilkan hasil berlabel "Sumber Eksternal".
7. Jika confidence **CUKUP** → bangun prompt: `[System Prompt] + [Context Chunks] + [Chat History] + [User Query]`.
8. Kirim prompt ke **Groq API**, terima generated response.
9. Response dikembalikan ke user beserta **referensi sumber dokumen**.

---

## 8. Milestones & Rollout Plan

### Fase 1 — MVP (Target: Web App Production-Ready)

| Milestone | Deliverable                                                             | Estimasi Durasi |
|-----------|-------------------------------------------------------------------------|-----------------|
| M1        | Setup infrastruktur: Vector DB, Backend API skeleton, Groq API integration | 1–2 minggu     |
| M2        | Document Ingestion Pipeline (PDF, DOCX, CSV) + Admin Panel Upload UI    | 2–3 minggu      |
| M3        | RAG Query Engine + Chat Web Interface (basic UI)                        | 2–3 minggu      |
| M4        | Google Search Fallback + Guardrails implementation                      | 1–2 minggu      |
| M5        | Internal Testing, Bug Fix, Performance Tuning                           | 1–2 minggu      |
| **Total** |                                                                         | **~7–12 minggu**|

---

### Fase 2 — Production Hardening

| Milestone | Deliverable                                                        |
|-----------|--------------------------------------------------------------------|
| M6        | Implementasi Autentikasi SSO (Google Workspace / Azure AD)         |
| M7        | REST API layer untuk integrasi sistem eksternal                    |
| M8        | Mobile App (iOS/Android)                                           |
| M9        | Enhanced Monitoring & Observability Dashboard                      |

---

### Fase 3 — Scale & Automation

| Milestone | Deliverable                                                                   |
|-----------|-------------------------------------------------------------------------------|
| M10       | Auto-sync knowledge base dari Google Drive / SharePoint / Confluence          |
| M11       | Migrasi LLM dari Groq API ke Self-hosted Open-Source Model                    |
| M12       | Role-based document access control (sesuai departemen/jabatan)                |

---

## 9. Success Metrics (KPIs)

### 9.1 Adoption & Usage

| Metrik                                           | Target (3 bulan post-launch) |
|--------------------------------------------------|------------------------------|
| Monthly Active Users (MAU)                       | ≥ 40% dari total user pool   |
| Jumlah query per hari (rata-rata)                | ≥ 100 query/hari             |
| User Retention Rate (minggu ke-4)                | ≥ 50%                        |

---

### 9.2 Quality & Accuracy

| Metrik                                                        | Target               |
|---------------------------------------------------------------|----------------------|
| Answer Relevance Rate (berdasarkan user feedback thumbs up/down) | ≥ 75% positif     |
| Fallback Rate (% query yang tidak terjawab dari KB internal)  | ≤ 20%               |
| Out-of-context rejection accuracy                             | ≥ 95% precision      |
| Hallucination Report Rate (user-flagged incorrect answers)   | ≤ 5%                |

---

### 9.3 Performance

| Metrik                                | Target     |
|---------------------------------------|------------|
| P95 Response Time                     | ≤ 5 detik  |
| System Uptime                         | ≥ 99.5%    |
| Document Indexing Success Rate        | ≥ 98%      |

---

### 9.4 Measurement Method

- **User Feedback:** Tombol 👍 / 👎 pada setiap respons chatbot; data disimpan di database untuk evaluasi berkala.
- **Query Logging:** Setiap query, confidence score, sumber respons (KB / Google / Rejected) dicatat untuk analisis.
- **Performance Monitoring:** APM tool (Prometheus + Grafana atau Datadog) untuk memantau latency dan uptime.
- **Monthly Review:** Evaluasi KPI oleh Product & Engineering setiap akhir bulan, dengan iterasi pada guardrails dan threshold jika diperlukan.

---

## 10. Open Issues & Assumptions

| ID    | Tipe        | Deskripsi                                                                                               |
|-------|-------------|---------------------------------------------------------------------------------------------------------|
| OI-01 | Assumption  | Groq API memiliki rate limit yang cukup untuk 200 concurrent users; perlu divalidasi dengan load test.  |
| OI-02 | Open Issue  | Pilihan Vector DB final (Qdrant vs Weaviate vs Pinecone) perlu diputuskan berdasarkan biaya dan kemudahan self-host di Fase 3. |
| OI-03 | Assumption  | Konteks bisnis spesifik yang diizinkan (untuk guardrails) akan didefinisikan oleh stakeholder sebelum M4. |
| OI-04 | Open Issue  | Google Custom Search API memiliki kuota harian; perlu diputuskan quota limit dan perilaku sistem ketika kuota habis. |
| OI-05 | Assumption  | Admin Panel pada MVP tidak memerlukan role management multi-admin; satu admin role sudah cukup.          |
| OI-06 | Open Issue  | Kebijakan data retention untuk conversation logs perlu diklarifikasi dengan tim legal/compliance.        |

---

*Document ini bersifat living document dan akan diperbarui seiring dengan perkembangan fase pengembangan.*
