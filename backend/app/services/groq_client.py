import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from groq import Groq, GroqError

from app.config import GROQ_API_KEY, GROQ_MODEL
from app.services.circuit_breaker import CircuitBreaker
from app.services.sanitizer import redact_pii

logger = logging.getLogger("chatbot")

_client = None
MAX_RETRIES = 3
_groq_circuit = CircuitBreaker("groq_api", failure_threshold=5, recovery_timeout=30.0)


def get_groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY, timeout=30.0)
    return _client


def _do_completion(client: Groq, messages: list[dict]):
    return client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.3,
        timeout=30,
    )


def rewrite_query(query: str, history: str) -> str:
    """Expand ambiguous or short queries using conversation history."""
    if not history:
        return query
    prompt = (
        "Kamu adalah asisten yang membantu memperjelas pertanyaan user. "
        "Berdasarkan riwayat percakapan berikut, tulis ulang pertanyaan terakhir "
        "agar berdiri sendiri (self-contained) dan mudah dipahami tanpa konteks sebelumnya. "
        "Balas HANYA dengan pertanyaan yang sudah ditulis ulang, tanpa penjelasan tambahan."
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Percakapan sebelumnya:\n{history}"},
        {"role": "user", "content": f"Pertanyaan user: {query}"},
    ]
    try:
        completion = _do_completion(get_groq(), messages)
        rewritten = completion.choices[0].message.content.strip()
        if rewritten and len(rewritten) < 500:
            logger.info("Rewrote query: '%s' -> '%s'", query[:50], rewritten[:80])
            return rewritten
    except Exception as e:
        logger.warning("Query rewrite failed: %s", str(e)[:100])
    return query


def rerank_chunks(query: str, chunks: list[dict]) -> list[dict]:
    """Filter chunks by binary relevance using Groq. Returns only relevant chunks."""
    if not chunks:
        return chunks

    items_text = "\n\n".join(
        f"[{i+1}] {c.get('file_name', '')}: {str(c.get('content', ''))[:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        "Kamu adalah filter relevansi dokumen. Berikut adalah daftar potongan dokumen "
        "dan sebuah pertanyaan user. Tentukan potongan mana yang RELEVAN untuk menjawab pertanyaan.\n\n"
        f"Pertanyaan: {query}\n\n"
        f"Potongan dokumen:\n{items_text}\n\n"
        "Balas dengan daftar nomor potongan yang relevan, dipisah koma. "
        "Contoh: 1, 3, 5\n"
        "Jika tidak ada yang relevan, balas: 0"
    )
    messages = [
        {"role": "system", "content": "Kamu adalah filter relevansi yang efisien. Balas singkat."},
        {"role": "user", "content": prompt},
    ]
    try:
        completion = _do_completion(get_groq(), messages)
        reply = completion.choices[0].message.content.strip()
        # If LLM explicitly says '0' or nothing, no chunk is relevant
        if reply.strip() == "0" or not reply.strip():
            logger.info("Rerank: LLM determined no chunks are relevant for this query")
            return []
        indices = [int(x.strip()) - 1 for x in re.split(r"[,;]", reply) if x.strip().isdigit()]
        relevant = [chunks[i] for i in indices if 0 <= i < len(chunks)]
        if not relevant:
            logger.info("Rerank: no valid indices parsed, returning empty")
            return []
        logger.info("Rerank: %d/%d chunks relevant", len(relevant), len(chunks))
        return relevant
    except Exception as e:
        logger.warning("Reranking failed: %s", str(e)[:100])
        return chunks


def format_context(chunks: list[dict], max_tokens: int = 2000) -> str:
    return _build_context(chunks, max_tokens)[0]


def format_context_with_ids(chunks: list[dict], max_tokens: int = 2000) -> tuple[str, dict[str, dict]]:
    """Format chunks and return (context_text, chunk_id_mapping).

    mapping = {"C1": {"chunk_id": ..., "file_name": ..., "page_number": ...}, ...}
    """
    return _build_context(chunks, max_tokens)


def _build_context(chunks: list[dict], max_tokens: int) -> tuple[str, dict[str, dict]]:
    """Build numbered chunk context with ID mapping."""
    parts = []
    mapping: dict[str, dict] = {}
    budget = max_tokens
    for i, chunk in enumerate(chunks):
        cid = f"C{i + 1}"
        content = chunk.get("content", "")
        file_name = chunk.get("file_name", "")
        page = chunk.get("page_number")
        row = chunk.get("row_index")

        header = f"[CHUNK {cid}]"
        source_label = f"File: {file_name}"
        if page:
            source_label += f" | Halaman: {page}"
        if row is not None:
            source_label += f" | Baris: {row}"

        block = f"{header}\n{source_label}\n{content}"
        content_len = len(block)
        estimated = content_len // 4  # rough token estimate

        if estimated > budget:
            if budget > 0:
                allowed_chars = budget * 4
                block = f"{header}\n{source_label}\n{content[:allowed_chars]}..."
                parts.append(block)
            break

        parts.append(block)
        budget -= estimated

        # Build mapping
        mapping[cid] = {
            "file_name": file_name,
            "page_number": page,
            "row_index": row,
            "chunk_id": chunk.get("chunk_id", cid),
            "document_id": chunk.get("document_id", ""),
        }

    return "\n\n".join(parts), mapping


_SYNONYM_STORE: dict[str, list[str]] | None = None


def _load_synonyms() -> dict[str, list[str]]:
    global _SYNONYM_STORE
    if _SYNONYM_STORE is not None:
        return _SYNONYM_STORE
    path = Path(__file__).parent.parent / "data" / "synonyms.json"
    if path.exists():
        try:
            _SYNONYM_STORE = json.loads(path.read_text(encoding="utf-8"))
            logger.info("Loaded %d synonym entries", len(_SYNONYM_STORE))
        except Exception as e:
            logger.warning("Failed to load synonyms: %s", str(e)[:100])
            _SYNONYM_STORE = {}
    else:
        _SYNONYM_STORE = {}
    return _SYNONYM_STORE


def expand_synonyms(query: str) -> str:
    """Expand query terms using domain synonym dictionary."""
    synonyms = _load_synonyms()
    if not synonyms:
        return query
    words = query.lower().split()
    expanded = list(words)
    for _i, w in enumerate(words):
        if w in synonyms:
            expanded.extend(synonyms[w])
    result = " ".join(dict.fromkeys(expanded))
    if result != query:
        logger.info("Synonym expansion: '%s' -> '%s'", query[:50], result[:80])
    return result


def insert_citations(reply: str, chunks: list[dict], threshold: float = 0.45) -> str:
    """Append compact, deduplicated source list at the end of the reply."""
    if not chunks or not reply:
        return reply

    seen = set()
    sources: list[str] = []
    for chunk in chunks:
        fn = chunk.get("file_name", "")
        if fn and fn not in seen:
            seen.add(fn)
            sources.append(fn)

    if not sources:
        return reply

    ref = " | ".join(sources)
    return f"{reply}\n\n---\nReferensi: {ref}"


def validate_citations(
    reply: str, chunk_mapping: dict[str, dict]
) -> tuple[str, list[dict]]:
    """Validate and reformat chunk-ID citations in LLM reply.

    Checks for patterns like [C1], [C2] in the reply text.
    Validates they exist in chunk_mapping.
    Replaces [C1] with proper source labels.

    Returns (clean_reply, citations_list).
    citations_list = [{"chunk_id": "...", "file_name": "...", "label": "C1"}, ...]
    """
    import re as _re

    citations: list[dict] = []
    if not chunk_mapping:
        return reply, citations

    # Find all [CX] patterns
    pattern = _re.compile(r"\[C(\d+)\]")
    found = pattern.findall(reply)

    seen = set()
    for num_str in found:
        cid = f"C{num_str}"
        if cid in seen:
            continue
        seen.add(cid)
        chunk_info = chunk_mapping.get(cid)
        if chunk_info:
            citations.append(
                {
                    "label": cid,
                    "file_name": chunk_info.get("file_name", ""),
                    "page_number": chunk_info.get("page_number"),
                    "row_index": chunk_info.get("row_index"),
                    "chunk_id": chunk_info.get("chunk_id", cid),
                    "document_id": chunk_info.get("document_id", ""),
                }
            )

    # Remove citations from the text completely since frontend displays sources separately
    clean_reply = _re.sub(r"\s*\[C\d+\](?:\s*\[C\d+\])*", "", reply)
    return clean_reply, citations


def is_citation_valid(reply: str, chunk_mapping: dict[str, dict]) -> bool:
    """Check if all citations in reply exist in mapping."""
    import re as _re

    if not chunk_mapping:
        return True  # no mapping = no validation needed

    found = _re.findall(r"\[C(\d+)\]", reply)
    if not found:
        # No explicit citations found - check if context suggests citations needed
        return True

    for num_str in found:
        if f"C{num_str}" not in chunk_mapping:
            logger.warning("Invalid citation: C%s not in mapping", num_str)
            return False
    return True


def generate_response(system_prompt: str, context: str, history: str, query: str) -> str:
    client = get_groq()
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.append({"role": "user", "content": f"Previous conversation:\n{history}"})
    if context:
        safe_context = redact_pii(context)
        messages.append({"role": "user", "content": f"Reference context:\n{safe_context}"})
    messages.append({"role": "user", "content": query})

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            completion = _groq_circuit.call(_do_completion, client, messages)
            return completion.choices[0].message.content or ""
        except GroqError as e:
            last_error = e
            status_code = getattr(e, "status_code", None)
            if status_code == 429 or (status_code and status_code >= 500):
                logger.warning(
                    "Groq API attempt %d/%d failed (status=%s): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    status_code,
                    str(e)[:100],
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2**attempt)
                    continue
            raise
        except Exception as e:
            last_error = e
            logger.warning(
                "Groq API attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, str(e)[:100]
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
                continue
            raise
    raise last_error


def generate_response_stream(system_prompt: str, context: str, history: str, query: str):
    """Generator that yields SSE event strings for streaming Groq response."""
    client = get_groq()
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.append({"role": "user", "content": f"Previous conversation:\n{history}"})
    if context:
        safe_context = redact_pii(context)
        messages.append({"role": "user", "content": f"Response context:\n{safe_context}"})
    messages.append({"role": "user", "content": query})

    for attempt in range(MAX_RETRIES):
        try:
            stream = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
                stream=True,
                timeout=30,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else ""
                if delta:
                    yield f"data: {json.dumps({'event': 'token', 'text': delta})}\n\n"
            break
        except GroqError as e:
            status_code = getattr(e, "status_code", None)
            if attempt < MAX_RETRIES - 1 and (
                status_code == 429 or (status_code and status_code >= 500)
            ):
                logger.warning("Groq stream attempt %d/%d failed", attempt + 1, MAX_RETRIES)
                time.sleep(2**attempt)
                continue
            yield f"data: {json.dumps({'event': 'error', 'text': 'Layanan AI sedang tidak tersedia.'})}\n\n"
            break
        except Exception as e:
            logger.warning(
                "Groq stream attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, str(e)[:100]
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
                continue
            yield f"data: {json.dumps({'event': 'error', 'text': 'Layanan AI sibuk, coba lagi.'})}\n\n"
            break
