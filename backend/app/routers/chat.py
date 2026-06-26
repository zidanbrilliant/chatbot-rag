import logging
import re
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import (
    MAX_HISTORY_TURNS,
    MAX_QUERY_LENGTH,
    SESSION_TIMEOUT_MINUTES,
)
from app.database import get_db
from app.middleware.auth import require_role
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import (
    FeedbackRequest,
    FeedbackResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.audit_log import log_web_search
from app.services.general_intent import OUT_OF_SCOPE_MESSAGE, classify_intent
from app.services.price_orchestrator import PriceQueryOrchestrator
from app.services.rag_orchestrator import RagOrchestrator, persist_message_citations
from app.services.sanitizer import scan_and_redact, scan_for_injection, validate_output_strict
from app.middleware.metrics import record_abstain, record_chat_intent
from app.services.search_cache import cache_search_results, get_cached_results
from app.services.search_client import search_web
from app.services.strict_mode import get_casual_response as _get_casual

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

logger = logging.getLogger("chatbot")


# ── Helpers ──────────────────────────────────────────


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
    text = text.translate(
        str.maketrans(
            "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～",
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
        )
    )
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_QUERY_LENGTH].strip()


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
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(MAX_HISTORY_TURNS * 2)
        .all()
    )
    return "\n".join(f"{m.role.capitalize()}: {m.content}" for m in messages)


def _search_web_with_cache(query: str) -> list[dict]:
    cached = get_cached_results(query)
    if cached is not None:
        return cached
    try:
        results = search_web(query, max_results=5)
    except Exception as e:
        logger.warning("web search failed: %s", str(e)[:120])
        return []
    # Convert SearchResult dataclass instances to dicts for downstream consumers
    # (web_filter, rag_orchestrator, response_formatter all use .get() on these)
    results_dicts = [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "score": r.score,
            "source_type": r.source_type,
        }
        for r in results
    ]
    cache_search_results(query, results_dicts)
    try:
        log_web_search(query=query, provider="duckduckgo", results_count=len(results_dicts), latency_ms=0)
    except Exception:
        pass
    return results_dicts


# ── Routes ───────────────────────────────────────────


@router.post("/query", response_model=QueryResponse)
def chat_query(
    req: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("viewer", "document_admin", "system_admin", "auditor")),
):
    query = _sanitize(req.query)
    query, _ = scan_and_redact(query)
    query, was_injected = scan_for_injection(query)
    if was_injected:
        logger.warning("Injection stripped from query: %s", req.query[:60])
    if not query:
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Silakan ketik pertanyaan yang jelas ya.",
        )

    # Layer 1b: reject prompt injection
    from app.services.prompt_guard import detect_injection
    inject_result = detect_injection(query)
    if inject_result.is_injection and inject_result.confidence >= 0.3:
        logger.warning(
            "Injection rejected: confidence=%.2f cat=%s query=%s",
            inject_result.confidence, inject_result.category, req.query[:60],
        )
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Maaf, saya hanya dapat membantu pertanyaan seputar informasi harga produk, perbandingan harga, dan konten dokumen di knowledge base. Silakan tanyakan hal yang lebih spesifik.",
        )

    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()
    db.add(ChatMessage(session_id=session.session_id, role="user", content=query))
    db.commit()

    # ── Intent routing (P1.2) ──
    intent_result = classify_intent(query)

    # Casual greeting
    if intent_result.intent == "casual_greeting" and intent_result.casual_response:
        reply = intent_result.casual_response
        record_chat_intent("casual_greeting", "answered")
        db.add(ChatMessage(session_id=session.session_id, role="assistant", content=reply))
        db.commit()
        return QueryResponse(session_id=session.session_id, reply=reply)

    # Out of scope
    if intent_result.intent == "out_of_scope":
        record_chat_intent("out_of_scope", "refused")
        record_abstain("out_of_scope")
        db.add(ChatMessage(session_id=session.session_id, role="assistant", content=OUT_OF_SCOPE_MESSAGE))
        db.commit()
        return QueryResponse(
            session_id=session.session_id,
            reply=OUT_OF_SCOPE_MESSAGE,
            confidence="abstain",
        )

    history = get_history(session.session_id, db)

    # ── Price query branch (delegated to orchestrator) ──
    if intent_result.intent == "price_query":
        record_chat_intent("price_query", "started")
        price_orchestrator = PriceQueryOrchestrator(db, _search_web_with_cache)
        price_response = price_orchestrator.run(query, history)
        if price_response is not None:
            record_chat_intent("price_query", "answered")
            clean_reply, _ = validate_output_strict(price_response.reply)
            price_response.reply = clean_reply
            price_response.session_id = session.session_id
            assistant_msg = ChatMessage(
                session_id=session.session_id,
                role="assistant",
                content=price_response.reply,
            )
            db.add(assistant_msg)
            db.commit()
            price_response.message_id = str(assistant_msg.id)
            return price_response

    # ── RAG branch (delegated to orchestrator) ──
    from app.services.response_formatter import STRICT_SYSTEM_PROMPT
    rag_orchestrator = RagOrchestrator(
        db=db,
        web_search_fn=_search_web_with_cache,
        system_prompt=STRICT_SYSTEM_PROMPT,
        user_role=user.role,
    )
    rag_result = rag_orchestrator.run(query, history)

    record_chat_intent("rag_question", "answered" if not rag_result["fallback_triggered"] else "fallback")
    if rag_result.get("out_of_context"):
        record_abstain(rag_result.get("confidence", "low"))

    assistant_msg = ChatMessage(
        session_id=session.session_id,
        role="assistant",
        content=rag_result["reply"],
    )
    db.add(assistant_msg)
    db.commit()

    # Persist internal citations
    if rag_result["citation_data"]:
        persist_message_citations(db, assistant_msg.id, rag_result["citation_data"])

    return QueryResponse(
        session_id=session.session_id,
        reply=rag_result["reply"],
        message_id=str(assistant_msg.id),
        sources=rag_result["sources"],
        confidence=rag_result["confidence"],
        out_of_context=rag_result["out_of_context"],
        fallback_triggered=rag_result["fallback_triggered"],
    )


@router.post("/feedback", response_model=FeedbackResponse)
def chat_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("viewer", "document_admin", "system_admin", "auditor")),
):
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
