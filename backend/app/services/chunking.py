from app.config import CHUNK_OVERLAP, CHUNK_SIZE

MAX_CHARS = 2000

# ── Inline recursive splitter ──────────────────────────────
# Ponytail: drop langchain-text-splitters dep. ~20 lines replace the lib.
# Splits on \n\n → \n → space → char, in priority order, with overlap.
_SEPARATORS = ["\n\n", "\n", " ", ""]


def _split_recursive(text: str, chunk_size: int, chunk_overlap: int, sep_idx: int = 0) -> list[str]:
    if len(text.split()) <= chunk_size:
        return [text]
    sep = _SEPARATORS[sep_idx]
    if sep == "":
        # Hard char-level split as last resort
        step = max(1, chunk_size - chunk_overlap)
        return [text[i : i + chunk_size] for i in range(0, len(text), step)]
    parts = text.split(sep) if sep else [text]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for p in parts:
        w = len(p.split())
        if current_words + w > chunk_size and current:
            joined = sep.join(current)
            if len(joined.split()) > chunk_size:
                # Recurse with next separator
                chunks.extend(_split_recursive(joined, chunk_size, chunk_overlap, sep_idx + 1))
            else:
                chunks.append(joined)
            # Keep overlap
            overlap_parts: list[str] = []
            overlap_words = 0
            for x in reversed(current):
                xw = len(x.split())
                if overlap_words + xw > chunk_overlap:
                    break
                overlap_parts.insert(0, x)
                overlap_words += xw
            current = overlap_parts
            current_words = overlap_words
        current.append(p)
        current_words += w
    if current:
        joined = sep.join(current)
        if len(joined.split()) > chunk_size:
            chunks.extend(_split_recursive(joined, chunk_size, chunk_overlap, sep_idx + 1))
        else:
            chunks.append(joined)
    return chunks


def _split_text(text: str) -> list[str]:
    return _split_recursive(text, CHUNK_SIZE, CHUNK_OVERLAP)


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
        return _split_text(text)

    header = "\n".join(header_lines)
    data_lines = lines[body_start:]

    preview_lines = data_lines[:10]
    chunk = header + "\n" + "\n".join(preview_lines) + "\n\n... (Data dipotong. Tabel ini memiliki banyak baris. Sistem akan menggunakan pembacaan otomatis via pandas jika ditanyakan tanggal/rentang spesifik)."

    return [chunk]


def chunk_document(docs: list[dict]) -> list[dict]:
    result = []
    for doc in docs:
        text = doc["text"]
        page = doc.get("page_number")

        if not text or not text.strip():
            continue

        if text.startswith("Konteks dokumen:"):
            chunks = _chunk_tabular(text)
            for c in chunks:
                result.append({"text": c, "page_number": page})
            continue

        raw = _split_text(text)
        for c in raw:
            if len(c) > MAX_CHARS:
                parts = [c[i : i + MAX_CHARS] for i in range(0, len(c), MAX_CHARS)]
                for p in parts:
                    result.append({"text": p, "page_number": page})
            else:
                result.append({"text": c, "page_number": page})
    return result
