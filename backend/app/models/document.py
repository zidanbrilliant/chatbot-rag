import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Enum as SAEnum
import enum

from app.database import Base


class DocumentStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.PROCESSING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
