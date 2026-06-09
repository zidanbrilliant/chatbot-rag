import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.database import Base


class RAGEvaluationCase(Base):
    __tablename__ = "rag_evaluation_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    expected_document_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    expected_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    category = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RAGEvaluationRun(Base):
    __tablename__ = "rag_evaluation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True), ForeignKey("rag_evaluation_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer = Column(Text, nullable=False)
    retrieved_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    metrics = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
