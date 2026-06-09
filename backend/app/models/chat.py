import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    @property
    def session_id(self) -> str:
        """Backward-compat: returns string UUID (legacy code uses .session_id)."""
        return str(self.id)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    query_original = Column(Text, nullable=True)
    query_rewritten = Column(Text, nullable=True)
    confidence = Column(String(10), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    token_usage = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chunk_id = Column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_start = Column(Integer, nullable=True)
    quote_end = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
