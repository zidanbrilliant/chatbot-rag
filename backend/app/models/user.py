import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserRole(str, enum.Enum):
    VIEWER = "viewer"
    DOCUMENT_ADMIN = "document_admin"
    SYSTEM_ADMIN = "system_admin"
    AUDITOR = "auditor"


ROLE_LEVEL = {
    "viewer": 0,
    "document_admin": 1,
    "system_admin": 2,
    "auditor": 3,
}


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
