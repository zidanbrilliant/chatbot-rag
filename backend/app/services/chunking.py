from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE

MAX_CHARS = 2000

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=lambda x: len(x.split()),
)


def _chunk_tabular(text: str) -> list[str]:
    lines = text.split("\n")
    header_lines = []
    body_start = 0
    for j, line in enumerate(lines):
        header_lines.append(line)
        if line.startswith("  [1] "):
            body_start = j
            break
    else:
        return _splitter.split_text(text)

    header = "\n".join(header_lines)
    data_lines = lines[body_start:]
    
    # Optimasasi: hanya simpan 10 baris pertama sebagai "summary chunk".
    # Semua query analitik tabular akan ditangani oleh structured_extractor yang membaca pandas langsung.
    preview_lines = data_lines[:10]
    chunk = header + "\n" + "\n".join(preview_lines) + "\n\n... (Data dipotong. Tabel ini memiliki banyak baris. Sistem akan menggunakan pembacaan otomatis via pandas jika ditanyakan tanggal/rentang spesifik)."
    
    return [chunk]


def chunk_document(docs: list[dict]) -> list[dict]:
    result = []
    for doc in docs:
        text = doc["text"]
        page = doc.get("page_number")
        
        if text.startswith("Konteks dokumen:"):
            chunks = _chunk_tabular(text)
            for c in chunks:
                result.append({"text": c, "page_number": page})
            continue

        raw = _splitter.split_text(text)
        for c in raw:
            if len(c) > MAX_CHARS:
                parts = [c[i : i + MAX_CHARS] for i in range(0, len(c), MAX_CHARS)]
                for p in parts:
                    result.append({"text": p, "page_number": page})
            else:
                result.append({"text": c, "page_number": page})
    return result
