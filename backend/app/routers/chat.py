import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import (
    HYBRID_TOP_K,
    MAX_HISTORY_TURNS,
    MAX_QUERY_LENGTH,
    QDRANT_COLLECTION,
    SESSION_TIMEOUT_MINUTES,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    FeedbackRequest,
    FeedbackResponse,
    QueryRequest,
    QueryResponse,
    Source,
)
from app.services.embedding import generate_embedding
from app.services.llm_client import (
    expand_synonyms,
    format_context_with_ids,
    format_hybrid_context,
    generate_response,
    generate_response_stream,
    insert_citations,
    is_citation_valid,
    rerank_chunks,
    rewrite_query,
    validate_citations,
)
from app.services.qdrant_client import get_qdrant, multi_source_search
from app.services.structured_extractor import extract_tabular_fact
from app.services.answerability import ABSTAIN_MESSAGE, evaluate as evaluate_answerability
from app.services.sanitizer import scan_and_redact
from app.services.search_client import search_web
from app.services.search_cache import get_cached_results, cache_search_results
from app.services.audit_log import log_web_search, log_rag_query

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

logger = logging.getLogger("chatbot")

SYSTEM_PROMPT = """\
Anda adalah chatbot knowledge base yang profesional dan akurat. \
Jawab berdasarkan informasi yang terdapat dalam CONTEXT yang diberikan di bawah. \
CONTEXT berisi dua jenis sumber: [INTERNAL C1, C2, ...] dari dokumen perusahaan, \
dan [EXTERNAL W1, W2, ...] dari pencarian web.

ATURAN MUTLAK:
1. Jawab berdasarkan informasi dari CONTEXT. Prioritaskan sumber INTERNAL jika tersedia.
2. Gunakan [C1], [C2], dst untuk mengutip sumber INTERNAL. Gunakan [W1], [W2], dst untuk mengutip sumber EXTERNAL.
3. Jika informasi tidak tersedia di CONTEXT, katakan bahwa informasi tidak ditemukan.
4. JANGAN membuat asumsi, mengarang, atau menebak.
5. Untuk data angka/tabel, KUTIP angkanya PERSIS dari CONTEXT tanpa membulatkan.
6. Untuk pertanyaan sapaan singkat (halo, hai, assalamualaikum), jawab santai dan singkat.
7. Gunakan Bahasa Indonesia yang profesional dan ringkas.
8. JANGAN sebutkan kata "CONTEXT", "CHUNK", "INTERNAL", "EXTERNAL", atau "berdasarkan teks" dalam jawaban.
9. Jawab langsung ke intinya — tidak perlu pembukaan panjang.
10. Jika menggunakan sumber web, sebutkan bahwa informasi berasal dari sumber online.
"""

CASUAL_PATTERNS = [
    r"^(hai|halo|hi|hey|hei|assalamualaikum|selamat\s+\w+)[\s!.]*$",
    r"^(apa\s+kabar|gimana\s+kabar|piye\s+kabar)[\s?!.]*$",
    r"^(tes|test|coba|testing)[\s!.]*$",
    r"^(kamu\s+siapa|siapa\s+kamu|nama\s+kamu|kamu\s+apa)[\s?!.]*$",
    r"^(terima\s+kasih|makasih|thanks|thank\s+you)[\s!.]*$",
    r"^(bisa\s+bahasa|kamu\s+bisa\s+apa|apa\s+saja\s+yang|bantu\s+apa)[\s?!.]*$",
]

FALLBACK_MESSAGE = (
    "Maaf, informasi tersebut tidak ditemukan di knowledge base maupun sumber online."
)

OOC_MESSAGE = (
    "Maaf, saya hanya bisa membantu pertanyaan seputar dokumen " "yang tersedia di knowledge base."
)


def _sanitize(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("\x00", "")
    text = re.sub(
        r"[\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\u2066\u2067\u2068\u2069\u202a\u202b\u202c\u202d\u202e\u2b0f\ufeff]",
        "",
        text,
    )
    text = re.sub(
        r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+(instructions?|prompt)|"
        r"system\s*:\s*|\[system\]|\[assistant\]|<\|system\|>)",
        "",
        text,
    )

    text = re.sub(r"https?://\S+", "", text)

    # Fullwidth-to-halfwidth normalization — RUF001 intentionally suppressed
    text = text.translate(
        str.maketrans(
            "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～",  # noqa: RUF001
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
        )
    )
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_QUERY_LENGTH].strip()


def _is_casual(query: str) -> bool:
    q = query.strip().lower()
    exact_casual = {"hai", "hi", "ya", "ok", "oke", "tes", "test", "halo"}
    if q in exact_casual:
        return True
    for pattern in CASUAL_PATTERNS:
        if re.match(pattern, q):
            return True
    return False


def get_or_create_session(session_id: str | None, db: Session) -> ChatSession:
    if session_id:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .with_for_update()
            .first()
        )
        if session:
            now = datetime.utcnow()
            if (
                session.updated_at
                and (now - session.updated_at).total_seconds() > SESSION_TIMEOUT_MINUTES * 60
            ):
                db.delete(session)
                db.commit()
                session = ChatSession(id=str(uuid.uuid4()))
                db.add(session)
                db.commit()
            return session
    session = ChatSession(id=str(uuid.uuid4()))
    db.add(session)
    db.commit()
    return session


def get_history(session_id: str, db: Session) -> str:
    turns = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_TURNS * 2)
        .all()
    )
    turns.reverse()
    lines = []
    for t in turns:
        prefix = "User" if t.role == "user" else "Assistant"
        lines.append(f"{prefix}: {t.content}")
    return "\n".join(lines)


def _search_web_with_cache(query: str) -> list[dict]:
    """Search web with Redis cache. Returns list of dicts with title, url, snippet."""
    cached = get_cached_results(query)
    if cached is not None:
        return cached

    t0 = time.time()
    results = search_web(query)
    latency_ms = int((time.time() - t0) * 1000)

    result_dicts = [
        {"title": r.title, "url": r.url, "snippet": r.snippet, "score": r.score}
        for r in results
    ]

    if result_dicts:
        cache_search_results(query, result_dicts)

    log_web_search(
        query=query,
        provider="duckduckgo",
        results_count=len(result_dicts),
        latency_ms=latency_ms,
    )

    return result_dicts


@router.post("/query", response_model=QueryResponse)
def chat_query(req: QueryRequest, db: Session = Depends(get_db)):
    query = _sanitize(req.query)
    query, pii_findings = scan_and_redact(query)
    
    if not query:
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Silakan ketik pertanyaan yang jelas ya.",
        )

    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()

    db.add(ChatMessage(session_id=session.session_id, role="user", content=query))
    db.commit()

    if _is_casual(query):
        reply = generate_response(SYSTEM_PROMPT, "", get_history(session.session_id, db), query)
        assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()
        return QueryResponse(
            session_id=session.session_id, reply=reply, message_id=str(assistant_msg.id)
        )

    history = get_history(session.session_id, db)

    if len(query.split()) > 10:
        enriched_query = query
    else:
        enriched_query = rewrite_query(query, history)
    enriched_query = expand_synonyms(enriched_query)

    try:
        query_embedding = generate_embedding(enriched_query)
    except Exception:
        query_embedding = None

    if query_embedding is None:
        reply = "Maaf, layanan sedang sibuk. Silakan coba lagi sebentar ya."
        assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()
        return QueryResponse(
            session_id=session.session_id, reply=reply, message_id=str(assistant_msg.id)
        )

    # ── Parallel: internal search (Qdrant) + web search (DuckDuckGo) ──
    web_results: list[dict] = []
    internal_future = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        internal_future = executor.submit(
            multi_source_search,
            query_vector=query_embedding,
            limit_per_file=4,
            score_threshold=0.3,
            with_vectors=True,
        )
        web_future = executor.submit(_search_web_with_cache, enriched_query)

        try:
            raw_results = internal_future.result(timeout=15)
        except Exception:
            raw_results = []

        try:
            web_results = web_future.result(timeout=15)
        except Exception:
            web_results = []

    if enriched_query != query:
        try:
            original_embedding = generate_embedding(query)
        except Exception:
            original_embedding = None
        if original_embedding is not None:
            orig_results = multi_source_search(
                query_vector=original_embedding,
                limit_per_file=4,
                score_threshold=0.3,
                with_vectors=True,
            )
            if orig_results and (not raw_results or orig_results[0].score > raw_results[0].score):
                raw_results = orig_results
                enriched_query = query

    if not raw_results:
        raw_results = multi_source_search(
            query_vector=query_embedding,
            limit_per_file=3,
            score_threshold=0.0,
            with_vectors=True,
        )
        if raw_results:
            logger.info("Progressive fallback: recovered %d results", len(raw_results))

    chunks = []
    for hit in raw_results:
        p = hit.payload
        if hit.score >= SIMILARITY_THRESHOLD:
            chunks.append(
                {
                    "file_name": p.get("file_name", ""),
                    "content": p.get("content", ""),
                    "page_number": p.get("page_number"),
                    "row_index": p.get("row_index"),
                    "score": hit.score,
                    "_vector": hit.vector if hasattr(hit, "vector") else None,
                }
            )

    if chunks:
        if len(chunks) > 5:
            chunks = rerank_chunks(enriched_query, chunks)
        chunks = [c for c in chunks if c.get("_vector") is not None]

    tabular_fact, tabular_file = extract_tabular_fact(enriched_query)
    if tabular_fact:
        logger.info("Structured fact extracted: %s", tabular_fact[:80])
        chunks.insert(0, {
            "file_name": tabular_file or "",
            "content": tabular_fact,
            "page_number": None,
            "row_index": None,
            "score": 1.0,
            "_vector": True
        })

    # ── Hybrid context: internal chunks + web results ──
    has_content = bool(chunks) or bool(web_results)
    if not has_content:
        assistant_msg = ChatMessage(
            session_id=session.session_id, role="assistant", content=FALLBACK_MESSAGE
        )
        db.add(assistant_msg)
        db.commit()
        return QueryResponse(
            session_id=session.session_id,
            reply=FALLBACK_MESSAGE,
            message_id=str(assistant_msg.id),
            confidence="abstain",
            fallback_triggered=True,
        )

    # Answerability gate (only for internal chunks — web results always pass)
    if chunks:
        gate = evaluate_answerability(chunks, query)
        if not gate.can_answer and not web_results:
            reply = ABSTAIN_MESSAGE
            assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
            db.add(assistant_msg)
            db.commit()
            return QueryResponse(
                session_id=session.session_id,
                reply=reply,
                message_id=str(assistant_msg.id),
                sources=[],
                confidence=gate.confidence,
                out_of_context=True,
            )
    else:
        from app.services.answerability import AnswerabilityResult
        gate = AnswerabilityResult(can_answer=True, confidence="medium", reason="web-only")

    if web_results:
        context, chunk_mapping = format_hybrid_context(chunks, web_results)
    else:
        context, chunk_mapping = format_context_with_ids(chunks)

    try:
        reply = generate_response(SYSTEM_PROMPT, context, history, enriched_query)
    except Exception:
        reply = "Maaf, layanan AI sedang tidak tersedia. Silakan coba lagi nanti."

    clean_reply, citation_data = validate_citations(reply, chunk_mapping)

    # Build sources from citations (both internal and external)
    seen_keys = set()
    sources = []
    for cit in citation_data:
        src_type = cit.get("source_type", "internal")
        if src_type == "external":
            url = cit.get("url", "")
            if url and url not in seen_keys:
                seen_keys.add(url)
                sources.append(Source(
                    source_type="external",
                    url=url,
                    title=cit.get("title", ""),
                ))
        else:
            fn = cit.get("file_name", "")
            if fn and fn not in seen_keys:
                seen_keys.add(fn)
                sources.append(Source(
                    file_name=fn,
                    page_number=cit.get("page_number"),
                    row_index=cit.get("row_index"),
                    source_type="internal",
                ))

    if not sources:
        for c in chunks[:TOP_K]:
            fn = c.get("file_name", "")
            if fn and fn not in seen_keys:
                seen_keys.add(fn)
                sources.append(Source(file_name=fn, source_type="internal"))
        for w in web_results[:3]:
            url = w.get("url", "")
            if url and url not in seen_keys:
                seen_keys.add(url)
                sources.append(Source(
                    source_type="external",
                    url=url,
                    title=w.get("title", ""),
                ))

    assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=clean_reply)
    db.add(assistant_msg)
    db.commit()

    from uuid import UUID as _UUID
    from app.models.chat import MessageCitation

    for cit in citation_data:
        if cit.get("source_type") == "external":
            continue
        try:
            cid_raw = cit.get("chunk_id")
            did_raw = cit.get("document_id")
            if not cid_raw or not did_raw:
                continue
            chunk_id = _UUID(cid_raw) if isinstance(cid_raw, str) else cid_raw
            doc_id = _UUID(did_raw) if isinstance(did_raw, str) else did_raw
            mc = MessageCitation(
                message_id=assistant_msg.id,
                chunk_id=chunk_id,
                document_id=doc_id,
                quote_start=None,
                quote_end=None,
            )
            db.add(mc)
        except (ValueError, AttributeError, TypeError):
            pass
    db.commit()

    return QueryResponse(
        session_id=session.session_id,
        reply=clean_reply,
        message_id=str(assistant_msg.id),
        sources=sources,
        confidence=gate.confidence,
    )


@router.post("/stream")
async def chat_stream(req: QueryRequest, db: Session = Depends(get_db)):
    query = _sanitize(req.query)
    query, pii_findings = scan_and_redact(query)
    
    if not query:
        return StreamingResponse(
            _sse_events("fallback", "Silakan ketik pertanyaan yang jelas ya."),
            media_type="text/event-stream",
        )

    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()

    db.add(ChatMessage(session_id=session.session_id, role="user", content=query))
    db.commit()

    if _is_casual(query):
        reply = generate_response(SYSTEM_PROMPT, "", get_history(session.session_id, db), query)
        assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()

        async def _casual_events():
            yield f'data: {json.dumps({"event": "token", "text": reply})}\n\n'
            await asyncio.sleep(0.01)
            yield f'data: {json.dumps({"event": "done", "reply": reply, "session_id": session.session_id, "message_id": str(assistant_msg.id)})}\n\n'

        return StreamingResponse(_casual_events(), media_type="text/event-stream")

    history = get_history(session.session_id, db)
    enriched_query = query

    # Only rewrite if there's conversation history
    if history.strip():
        enriched_query = rewrite_query(query, history)

    enriched_query = expand_synonyms(enriched_query)

    try:
        query_embedding = generate_embedding(enriched_query)
    except Exception:
        query_embedding = None

    if query_embedding is None:
        return StreamingResponse(
            _sse_events("error", "Maaf, layanan sedang sibuk. Coba lagi."),
            media_type="text/event-stream",
        )

    # ── Multi-source search: fetch top-K per file to prevent domain flooding ──
    raw_results = multi_source_search(
        query_vector=query_embedding,
        limit_per_file=4,
        score_threshold=0.3,
        with_vectors=True,
    )

    if enriched_query != query:
        try:
            original_embedding = generate_embedding(query)
        except Exception:
            original_embedding = None
        if original_embedding is not None:
            orig_results = multi_source_search(
                query_vector=original_embedding,
                limit_per_file=4,
                score_threshold=0.3,
                with_vectors=True,
            )
            if orig_results and (not raw_results or orig_results[0].score > raw_results[0].score):
                raw_results = orig_results
                enriched_query = query

    if not raw_results:
        raw_results = multi_source_search(
            query_vector=query_embedding,
            limit_per_file=3,
            score_threshold=0.0,
            with_vectors=True,
        )
        if raw_results:
            logger.info("Progressive fallback: recovered %d results", len(raw_results))

    if not raw_results:
        assistant_msg = ChatMessage(
            session_id=session.session_id, role="assistant", content=FALLBACK_MESSAGE
        )
        db.add(assistant_msg)
        db.commit()
        return StreamingResponse(
            _sse_events(
                "fallback",
                FALLBACK_MESSAGE,
                session_id=session.session_id,
                message_id=str(assistant_msg.id),
            ),
            media_type="text/event-stream",
        )

    chunks = []
    for hit in raw_results:
        p = hit.payload
        if hit.score >= SIMILARITY_THRESHOLD:
            chunks.append(
                {
                    "file_name": p.get("file_name", ""),
                    "content": p.get("content", ""),
                    "page_number": p.get("page_number"),
                    "row_index": p.get("row_index"),
                    "score": hit.score,
                    "_vector": hit.vector if hasattr(hit, "vector") else None,
                }
            )

    if chunks:
        # Only rerank if there are many candidates
        if len(chunks) > 5:
            chunks = rerank_chunks(enriched_query, chunks)
        chunks = [c for c in chunks if c.get("_vector") is not None]

    tabular_fact, tabular_file = extract_tabular_fact(enriched_query)
    if tabular_fact:
        logger.info("Structured fact extracted: %s", tabular_fact[:80])
        chunks.insert(0, {
            "file_name": tabular_file or "",
            "content": tabular_fact,
            "page_number": None,
            "row_index": None,
            "score": 1.0,
            "_vector": True
        })

    if not chunks:
        assistant_msg = ChatMessage(
            session_id=session.session_id, role="assistant", content=FALLBACK_MESSAGE
        )
        db.add(assistant_msg)
        db.commit()
        return StreamingResponse(
            _sse_events(
                "fallback",
                FALLBACK_MESSAGE,
                session_id=session.session_id,
                message_id=str(assistant_msg.id),
            ),
            media_type="text/event-stream",
        )

    # ── Answerability Gate ───────────────────────────
    gate = evaluate_answerability(chunks, query)
    if not gate.can_answer:
        reply = ABSTAIN_MESSAGE
        assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()
        
        async def abstain_events():
            yield f'data: {json.dumps({"event": "token", "text": reply})}\n\n'
            await asyncio.sleep(0.01)
            yield f'data: {json.dumps({"event": "done", "reply": reply, "session_id": session.session_id, "message_id": str(assistant_msg.id), "sources": []})}\n\n'
            
        return StreamingResponse(abstain_events(), media_type="text/event-stream")

    context = format_context(chunks)
    sources = [
        {
            "file_name": c["file_name"],
            "page_number": c.get("page_number"),
            "row_index": c.get("row_index"),
        }
        for c in chunks[:TOP_K]
    ]

    async def event_generator():
        try:
            full_reply = ""
            for event_str in generate_response_stream(
                SYSTEM_PROMPT, context, history, enriched_query
            ):
                event_data = json.loads(event_str[6:])  # strip "data: " prefix
                if event_data.get("event") == "token":
                    full_reply += event_data["text"]
                elif event_data.get("event") == "error":
                    yield event_str
                    full_reply = event_data["text"]
                    break
                yield event_str

            cited_reply = full_reply
            assistant_msg = ChatMessage(
                session_id=session.session_id, role="assistant", content=cited_reply
            )
            db.add(assistant_msg)
            db.commit()

            done_event = {
                "event": "done",
                "session_id": session.session_id,
                "message_id": str(assistant_msg.id),
                "sources": sources,
                "reply": cited_reply,
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception as e:
            logger.error("Stream error: %s", str(e))
            yield f"data: {json.dumps({'event': 'error', 'text': 'Terjadi kesalahan. Coba lagi.'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse_events(event_type: str, text: str, session_id: str = "", message_id: str = ""):
    payload = {"event": event_type, "text": text}
    if session_id:
        payload["session_id"] = session_id
    if message_id:
        payload["message_id"] = message_id
    yield f"data: {json.dumps(payload)}\n\n"


@router.post("/feedback", response_model=FeedbackResponse)
def chat_feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    if req.feedback not in ("positive", "negative"):
        raise HTTPException(400, "Feedback harus 'positive' atau 'negative'")

    if not req.message_id or not req.message_id.strip():
        raise HTTPException(400, "message_id tidak boleh kosong")

    msg = db.query(ChatMessage).filter(ChatMessage.id == req.message_id).first()
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan")

    msg.feedback = req.feedback
    db.commit()
    return FeedbackResponse(message="Feedback tersimpan")
