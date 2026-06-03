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
from app.config import QDRANT_COLLECTION, TOP_K, SIMILARITY_THRESHOLD, MAX_HISTORY_TURNS, SESSION_TIMEOUT_MINUTES

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

SYSTEM_PROMPT = """\
Kamu adalah asisten AI pribadi yang ramah. \
Kamu bisa ngobrol santai dan menjawab sapaan. \
Kalau kamu menerima konteks/referensi dari dokumen, jawab pertanyaan \
berdasarkan konteks tersebut dan sebut nama file sumbernya. \
Kalau tidak ada konteks sama sekali dan pertanyaan sangat jauh dari topik umum, \
tolak dengan sopan. \
Gunakan bahasa Indonesia yang santai."""


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
    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()

    db.add(ChatHistory(session_id=session.session_id, role="user", content=req.query))
    db.commit()

    query_embedding = generate_embedding(req.query)
    qdrant = get_qdrant()
    search_result = qdrant.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_embedding,
        limit=TOP_K,
        score_threshold=SIMILARITY_THRESHOLD,
    )

    if not search_result:
        intent_check = generate_response(
            SYSTEM_PROMPT,
            "",
            "",
            f"User bilang: '{req.query}'. Apakah ini pertanyaan umum/sapaan biasa atau pertanyaan yang butuh dokumen internal? Jawab 'umum' atau 'dokumen'."
        )
        if "dokumen" in intent_check.lower():
            db.add(ChatHistory(session_id=session.session_id, role="assistant",
                               content="Informasi ini tidak ditemukan dalam knowledge base perusahaan. Apakah kamu ingin saya carikan dari sumber eksternal?"))
            db.commit()
            return QueryResponse(
                session_id=session.session_id,
                reply="Informasi ini tidak ditemukan dalam knowledge base perusahaan. Aku bisa bantu cari dari sumber eksternal kalau kamu mau.",
                fallback_triggered=True,
            )

        reply = generate_response(SYSTEM_PROMPT, "", get_history(session.session_id, db), req.query)
        db.add(ChatHistory(session_id=session.session_id, role="assistant", content=reply))
        db.commit()
        return QueryResponse(
            session_id=session.session_id,
            reply=reply,
        )

    context_parts = []
    sources = []
    for hit in search_result:
        payload = hit.payload
        context_parts.append(payload["content"])
        sources.append(Source(
            file_name=payload.get("file_name", ""),
            page_number=payload.get("page_number"),
            row_index=payload.get("row_index"),
        ))

    context = "\n\n".join(context_parts)
    history = get_history(session.session_id, db)

    try:
        reply = generate_response(SYSTEM_PROMPT, context, history, req.query)
    except Exception:
        reply = "Maaf, layanan AI sedang tidak tersedia. Silakan coba lagi nanti."

    db.add(ChatHistory(session_id=session.session_id, role="assistant", content=reply))
    db.commit()

    is_out_of_context = "tidak bisa membantu" in reply.lower() or "di luar" in reply.lower() and "tidak" in reply.lower()

    return QueryResponse(
        session_id=session.session_id,
        reply=reply,
        sources=sources,
        out_of_context=is_out_of_context,
    )


@router.post("/fallback", response_model=FallbackResponse)
def chat_fallback(req: FallbackRequest, db: Session = Depends(get_db)):
    import requests as http_requests
    from app.config import GOOGLE_API_KEY, GOOGLE_CSE_ID

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise HTTPException(503, "Google Search API not configured")

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
    except Exception as e:
        raise HTTPException(502, f"Google Search failed: {str(e)}")
