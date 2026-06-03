# TASKS.md
# Development Flow & Milestone Tracking

---

## Milestone 1: Setup Infrastruktur (Target: 1-2 Minggu)
*Fokus: Mempersiapkan pondasi repository, database, dan koneksi LLM.*

- [x] **T-1.1:** Inisialisasi repository backend (FastAPI) dan frontend (Web App - e.g., React/Streamlit).
- [x] **T-1.2:** Setup container Docker Compose untuk Backend, Vector DB (Qdrant), dan RDBMS (PostgreSQL/SQLite).
- [x] **T-1.3:** Setup koneksi client ke Qdrant dan pastikan collection `company_knowledge_base` terbentuk saat startup.
- [x] **T-1.4:** Setup HTTP Client / SDK untuk Groq API dan buat fungsi wrapper dasar untuk inferensi.
- [x] **T-1.5:** Buat model database SQLAlchemy untuk tabel `documents`, `chat_sessions`, dan `chat_history`.

## Milestone 2: Document Ingestion Pipeline (Target: 2-3 Minggu)
*Fokus: Parsing file, chunking, embedding, dan UI Admin.*

- [x] **T-2.1:** Buat endpoint `POST /api/v1/documents/upload` dengan validasi ukuran file (Max 50MB) dan ekstensi (pdf, docx, csv, xlsx).
- [x] **T-2.2:** Implementasi document parsers:
    - [x] PyMuPDF / pdfplumber untuk PDF.
    - [x] library python-docx untuk DOCX (ekstraksi teks dan heading).
    - [x] Pandas untuk ekstraksi CSV/Excel dengan injeksi header kolom.
- [x] **T-2.3:** Implementasi sistem chunking (Max 512 tokens, 50 overlap) menggunakan framework seperti LangChain/LlamaIndex.
- [x] **T-2.4:** Implementasi embedding generation dan upsert payload ke Qdrant (termasuk UUID relasional untuk metadata).
- [x] **T-2.5:** Buat endpoint `GET` dan `DELETE` untuk manajemen dokumen.
- [x] **T-2.6:** Bangun Admin Panel UI (Web App) untuk upload file, list dokumen, status ingestion, dan tombol delete.

## Milestone 3: RAG Query Engine & Chat UI (Target: 2-3 Minggu)
*Fokus: Semantic search, perakitan prompt, inferensi, dan UI Karyawan.*

- [x] **T-3.1:** Implementasi mekanisme penyisipan session ke DB (Create & Update `chat_sessions` dan `chat_history`).
- [x] **T-3.2:** Buat logic mengubah `user_query` menjadi embedding vector.
- [x] **T-3.3:** Eksekusi similarity search ke Qdrant dan implementasi logic *Top-K* return chunks (K=3 hingga 5).
- [x] **T-3.4:** Susun system prompt yang mengikat LLM dengan batas konteks bisnis perusahaan.
- [x] **T-3.5:** Buat endpoint `POST /api/v1/chat/query` yang merakit prompt (`System + Konteks + History + Query`) dan mengeksekusi request ke Groq API.
- [x] **T-3.6:** Mapping respons Groq API ke format JSON balasan termasuk referensi sitasi/metadata file asal.
- [x] **T-3.7:** Bangun Chat UI (Web App) lengkap dengan render riwayat pesan dan penanda sesi (Session Management).

## Milestone 4: Fallback & Guardrails (Target: 1-2 Minggu)
*Fokus: Eksekusi Edge Case (Similarity rendah & Out-of-Context).*

- [x] **T-4.1:** Terapkan deteksi similarity score (Threshold ≥ 0.75). Jika seluruh chunk di bawah threshold, return flag `fallback_triggered = true`.
- [x] **T-4.2:** Integrasikan Google Custom Search JSON API pada endpoint `POST /api/v1/chat/fallback`.
- [x] **T-4.3:** Perbarui Chat UI untuk menampilkan prompt "Semi-Manual" (tombol Ya/Tidak) jika menerima flag fallback.
- [x] **T-4.4:** Tambahkan parsing penolakan elegan ("Maaf, saya hanya membantu konteks...") dari system prompt/guardrails pipeline, pastikan UI me-render respons ini secara rapi.
- [x] **T-4.5:** Pastikan log (JSON terstruktur) mencatat trigger out-of-context dan fallback untuk keperluan analitik.

## Milestone 5: Testing, Bug Fix & Performance (Target: 1-2 Minggu)
*Fokus: Stabilitas, P95 metrics, dan finalisasi.*

- [x] **T-5.1:** Lakukan unit test untuk fungsi parsing dan chunking dokumen.
- [x] **T-5.2:** Lakukan integrasi End-to-End testing pada alur Chat (Normal, Fallback, dan Rejected).
- [x] **T-5.3:** Konfigurasi environment variables agar nama model, max chunk, dan threshold confidence dinamis (tanpa re-build Docker).
- [x] **T-5.4:** Verifikasi Response Time ≤ 5 detik dan Document Ingestion Time ≤ 60 detik.
- [x] **T-5.5:** Penyerahan (Handover) untuk Engineering Review sebelum tahap hard-launch MVP.
