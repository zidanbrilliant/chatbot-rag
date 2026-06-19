import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    DELETED = "deleted"


class AccessLevel(str, enum.Enum):
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(Text, nullable=False)
    stored_filename = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(10), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    document_hash = Column(String(64), nullable=True, index=True)
    access_level = Column(
        SAEnum(AccessLevel, native_enum=False, length=20, values_callable=lambda obj: [e.value for e in obj]),
        default="internal",
        nullable=False,
    )
    status = Column(
        SAEnum(DocumentStatus, native_enum=False, length=20, values_callable=lambda obj: [e.value for e in obj]),
        default="uploaded",
        nullable=False,
    )
    version = Column(Integer, default=1, nullable=False)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    attributes = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index = Column(Integer, nullable=False)
    text_hash = Column(String(64), nullable=False)
    page_number = Column(Integer, nullable=True)
    sheet_name = Column(Text, nullable=True)
    section_title = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    qdrant_point_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
