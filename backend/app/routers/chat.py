import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat import ChatSession, ChatHistory
from app.schemas.chat import QueryRequest, QueryResponse, FallbackRequest, FallbackResponse, Source, ExternalSource
from app.services.embedding import generate_embedding
from app.services.qdrant_client import get_qdrant
from app.services.groq_client import generate_response
from app.config import (
    QDRANT_COLLECTION, TOP_K, SIMILARITY_THRESHOLD,
    MAX_HISTORY_TURNS, SESSION_TIMEOUT_MINUTES, MAX_QUERY_LENGTH,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

SYSTEM_PROMPT = """\
Kamu adalah asisten AI pribadi yang membantu menjawab pertanyaan berdasarkan dokumen yang tersedia. \

ATURAN UTAMA:
1. Kamu boleh ngobrol santai dan menjawab sapaan seperti "halo", "apa kabar".
2. Jika diberikan konteks/referensi dokumen, JAWAB berdasarkan konteks tersebut. \
Sebutkan nama file sumbernya. Jangan menolak — konteks yang diberikan berarti topiknya relevan.
3. Jika TIDAK ada konteks dan pertanyaannya adalah pertanyaan serius (bukan sapaan), \
TOLAK dengan pesan: "Maaf, saya hanya bisa membantu pertanyaan seputar dokumen yang tersedia di knowledge base."
4. Jangan pernah mengaku bisa melakukan hal di luar kemampuannya sebagai asisten dokumen.
5. Gunakan bahasa Indonesia yang santai dan ramah."""

CASUAL_PATTERNS = [
    r"^(hai|halo|hi|hey|hei|assalamualaikum|selamat\s+\w+)[\s!.]*$",
    r"^(apa\s+kabar|gimana\s+kabar|piye\s+kabar)[\s?!.]*$",
    r"^(tes|test|coba|testing)[\s!.]*$",
    r"^(kamu\s+siapa|siapa\s+kamu|nama\s+kamu|kamu\s+apa)[\s?!.]*$",
    r"^(terima\s+kasih|makasih|thanks|thank\s+you)[\s!.]*$",
    r"^(bisa\s+bahasa|kamu\s+bisa\s+apa|apa\s+saja\s+yang|bantu\s+apa)[\s?!.]*$",
]

FALLBACK_MESSAGE = (
    "Maaf, informasi tersebut tidak ditemukan di knowledge base. "
    "Mau saya carikan di Google?"
)

OOC_MESSAGE = (
    "Maaf, saya hanya bisa membantu pertanyaan seputar dokumen "
    "yang tersedia di knowledge base."
)


def _sanitize(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("\x00", "")
    text = re.sub(r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+(instructions?|prompt)|"
                  r"system\s*:\s*|\[system\]|\[assistant\]|<\|system\|>)", "", text)
    return text[:MAX_QUERY_LENGTH].strip()


def _is_casual(query: str) -> bool:
    q = query.strip().lower()
    if len(q) <= 3:
        return True
    for pattern in CASUAL_PATTERNS:
        if re.match(pattern, q):
            return True
    return False


def get_or_create_session(session_id: str | None, db: Session) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if session:
            now = datetime.utcnow()
            if session.updated_at and (now - session.updated_at).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
                session = ChatSession(session_id=str(uuid.uuid4()))
                db.add(session)
            return session
    session = ChatSession(session_id=str(uuid.uuid4()))
    db.add(session)
    db.commit()
    return session


def get_history(session_id: str, db: Session) -> str:
    turns = (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.created_at.desc())
        .limit(MAX_HISTORY_TURNS * 2)
        .all()
    )
    turns.reverse()
    lines = []
    for t in turns:
        prefix = "User" if t.role == "user" else "Assistant"
        lines.append(f"{prefix}: {t.content}")
    return "\n".join(lines)


@router.post("/query", response_model=QueryResponse)
def chat_query(req: QueryRequest, db: Session = Depends(get_db)):
    query = _sanitize(req.query)
    if not query:
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Silakan ketik pertanyaan yang jelas ya.",
        )

    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()

    db.add(ChatHistory(session_id=session.session_id, role="user", content=query))
    db.commit()

    query_embedding = generate_embedding(query)
    qdrant = get_qdrant()
    search_result = qdrant.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_embedding,
        limit=TOP_K,
        score_threshold=SIMILARITY_THRESHOLD,
    )

    if not search_result:
        if _is_casual(query):
            reply = generate_response(SYSTEM_PROMPT, "", get_history(session.session_id, db), query)
            db.add(ChatHistory(session_id=session.session_id, role="assistant", content=reply))
            db.commit()
            return QueryResponse(session_id=session.session_id, reply=reply)

        db.add(ChatHistory(session_id=session.session_id, role="assistant", content=FALLBACK_MESSAGE))
        db.commit()
        return QueryResponse(
            session_id=session.session_id,
            reply=FALLBACK_MESSAGE,
            fallback_triggered=True,
        )

    context_parts = []
    sources = []
    best_score = 0.0
    for hit in search_result:
        if hit.score > best_score:
            best_score = hit.score
        payload = hit.payload
        content = payload.get("content", "")[:800]
        context_parts.append(f"[Sumber: {payload.get('file_name', '')}] {content}")
        sources.append(Source(
            file_name=payload.get("file_name", ""),
            page_number=payload.get("page_number"),
            row_index=payload.get("row_index"),
        ))

    context = "\n\n---\n\n".join(context_parts)
    history = get_history(session.session_id, db)

    out_of_context = False
    try:
        reply = generate_response(SYSTEM_PROMPT, context, history, query)
    except Exception:
        reply = "Maaf, layanan AI sedang tidak tersedia. Silakan coba lagi nanti."

    lower_reply = reply.lower()
    if any(phrase in lower_reply for phrase in [
        "tidak bisa membantu", "tidak bisa menjawab", "di luar konteks",
        "saya hanya bisa", "saya hanya dapat",
    ]):
        out_of_context = True
        reply = OOC_MESSAGE

    db.add(ChatHistory(session_id=session.session_id, role="assistant", content=reply))
    db.commit()

    return QueryResponse(
        session_id=session.session_id,
        reply=reply,
        sources=sources,
        out_of_context=out_of_context,
    )


@router.post("/fallback", response_model=FallbackResponse)
def chat_fallback(req: FallbackRequest, db: Session = Depends(get_db)):
    import requests as http_requests
    from app.config import GOOGLE_API_KEY, GOOGLE_CSE_ID

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise HTTPException(503, "Google Search API tidak tersedia")

    try:
        resp = http_requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": req.query},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        external_sources = [
            ExternalSource(title=item.get("title", ""), url=item.get("link", ""))
            for item in items[:5]
        ]
        snippets = [item.get("snippet", "") for item in items[:3]]
        reply = "Hasil pencarian dari sumber eksternal:\n\n" + "\n\n".join(snippets) if snippets else "Tidak ada hasil ditemukan."

        db.add(ChatHistory(session_id=req.session_id, role="assistant", content=reply))
        db.commit()
        return FallbackResponse(reply=reply, external_sources=external_sources)

    except Exception:
        raise HTTPException(502, "Pencarian Google gagal. Coba lagi nanti.")
