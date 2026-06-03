# SPEC.md
# API Specification & Data Schema

---

## 1. DATA SCHEMA (SCHEMA.md)

### 1.1. Vector Database Schema (Qdrant)
Menyimpan vector embeddings dan metadata chunk dokumen.

* **Collection Name:** `company_knowledge_base`
* **Vector Dimension:** `768` (Asumsi menggunakan model embedding seperti `nomic-embed-text` atau sejenisnya)
* **Distance Metric:** `Cosine`
* **Payload (Metadata) Schema:**
    ```json
    {
      "chunk_id": "string (UUID)",
      "document_id": "string (UUID) - Relasi ke RDBMS",
      "file_name": "string",
      "content": "string (Teks aktual dari chunk, max 512 tokens)",
      "page_number": "integer (Nullable, untuk PDF/DOCX)",
      "row_index": "integer (Nullable, untuk CSV/Excel)"
    }
    ```

### 1.2. Relational Database Schema (PostgreSQL / SQLite)
Menyimpan status dokumen dan riwayat sesi chat.

**Table: `documents`**
| Column       | Type         | Constraints                  | Description                               |
|--------------|--------------|------------------------------|-------------------------------------------|
| `id`         | UUID         | Primary Key                  | Identifier unik dokumen                   |
| `file_name`  | VARCHAR(255) | Not Null                     | Nama asli file yang diupload              |
| `file_size`  | INTEGER      | Not Null                     | Ukuran file dalam bytes                   |
| `status`     | VARCHAR(50)  | Default 'PROCESSING'         | Status: PROCESSING, INDEXED, FAILED       |
| `created_at` | TIMESTAMP    | Default CURRENT_TIMESTAMP    | Waktu upload                              |

**Table: `chat_sessions`**
| Column       | Type         | Constraints                  | Description                               |
|--------------|--------------|------------------------------|-------------------------------------------|
| `session_id` | UUID         | Primary Key                  | Identifier sesi chat                      |
| `created_at` | TIMESTAMP    | Default CURRENT_TIMESTAMP    | Waktu sesi dibuat                         |
| `updated_at` | TIMESTAMP    | Default CURRENT_TIMESTAMP    | Diupdate tiap ada pesan baru              |

**Table: `chat_history`**
| Column       | Type         | Constraints                  | Description                               |
|--------------|--------------|------------------------------|-------------------------------------------|
| `id`         | UUID         | Primary Key                  | Identifier unik pesan                     |
| `session_id` | UUID         | Foreign Key (chat_sessions)  | Relasi ke sesi                            |
| `role`       | VARCHAR(10)  | Not Null                     | 'user' atau 'assistant'                   |
| `content`    | TEXT         | Not Null                     | Isi pesan                                 |
| `created_at` | TIMESTAMP    | Default CURRENT_TIMESTAMP    | Waktu pesan dikirim                       |

---

## 2. API SPECIFICATION (API_SPEC.md)

### 2.1. Chat & RAG Engine

#### POST `/api/v1/chat/query`
Mengirim pertanyaan user dan mendapatkan respons dari RAG pipeline.

* **Request Body:**
    ```json
    {
      "session_id": "string (UUID, opsional - generate baru jika kosong)",
      "query": "string (Pertanyaan user)"
    }
    ```
* **Response (200 OK - Success with Context):**
    ```json
    {
      "session_id": "123e4567-e89b-12d3-a456-426614174000",
      "reply": "Teks respons dari Groq LLM berdasarkan konteks...",
      "sources": [
        {"file_name": "SOP_HR.pdf", "page_number": 12},
        {"file_name": "Kebijakan_Cuti.docx"}
      ],
      "fallback_triggered": false,
      "out_of_context": false
    }
    ```
* **Response (200 OK - Fallback Triggered / Out of Context):**
    ```json
    {
      "session_id": "123e4567-e89b-12d3-a456-426614174000",
      "reply": "Informasi ini tidak ditemukan dalam knowledge base perusahaan. Apakah kamu ingin saya carikan dari sumber eksternal?",
      "sources": [],
      "fallback_triggered": true,
      "out_of_context": false
    }
    ```

#### POST `/api/v1/chat/fallback`
Mengeksekusi pencarian ke Google Custom Search JSON API jika user setuju.

* **Request Body:**
    ```json
    {
      "session_id": "string (UUID)",
      "query": "string (Pertanyaan user)"
    }
    ```
* **Response (200 OK):**
    ```json
    {
      "reply": "Ringkasan jawaban dari Google...",
      "external_sources": [
        {"title": "Judul Artikel", "url": "[https://example.com/artikel](https://example.com/artikel)"}
      ]
    }
    ```

### 2.2. Document Management

#### POST `/api/v1/documents/upload`
Upload dokumen ke sistem untuk di-ingest ke Vector DB.

* **Content-Type:** `multipart/form-data`
* **Payload:** `file` (Binary, max 50MB)
* **Response (202 Accepted):**
    ```json
    {
      "document_id": "987fcdeb-51a2-43d7-9012-426614174000",
      "message": "Upload berhasil. Ingestion sedang diproses."
    }
    ```

#### GET `/api/v1/documents`
Mendapatkan daftar dokumen di knowledge base.

* **Response (200 OK):**
    ```json
    {
      "data": [
        {
          "id": "987fcdeb...",
          "file_name": "SOP_Finance.pdf",
          "file_size": 1048576,
          "status": "INDEXED",
          "created_at": "2026-06-03T10:00:00Z"
        }
      ]
    }
    ```

#### DELETE `/api/v1/documents/{document_id}`
Menghapus dokumen dari RDBMS dan menghapus semua vektor terkait dari Vector DB.

* **Response (200 OK):**
    ```json
    {
      "message": "Dokumen dan vektor terkait berhasil dihapus."
    }
    ```