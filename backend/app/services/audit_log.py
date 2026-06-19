import logging
import uuid
from datetime import datetime

from app.database import SessionLocal
from app.models.audit import AuditLog

logger = logging.getLogger("chatbot")


def log_event(
    event_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write one audit log entry. Never raises — failures are swallowed."""
    try:
        db = SessionLocal()
        try:
            entry = AuditLog(
                id=uuid.uuid4(),
                event_type=event_type,
                resource_type=resource_type,
                resource_id=uuid.UUID(resource_id) if resource_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                event_metadata=metadata or {},
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Audit log write failed: %s", str(e)[:120])


def log_web_search(
    query: str,
    provider: str,
    results_count: int,
    latency_ms: int,
    session_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Audit log for a web search call."""
    log_event(
        event_type="web_search",
        resource_type="chat",
        resource_id=session_id,
        ip_address=ip_address,
        metadata={
            "query": query[:200],
            "provider": provider,
            "results_count": results_count,
            "latency_ms": latency_ms,
        },
    )


def log_rag_query(
    session_id: str | None,
    query: str,
    internal_chunks: int,
    web_results: int,
    confidence: str,
    latency_ms: int,
    ip_address: str | None = None,
) -> None:
    """Audit log for a RAG query."""
    log_event(
        event_type="rag_query",
        resource_type="chat",
        resource_id=session_id,
        ip_address=ip_address,
        metadata={
            "query": query[:200],
            "internal_chunks": internal_chunks,
            "web_results": web_results,
            "confidence": confidence,
            "latency_ms": latency_ms,
        },
    )
