from .audit import AuditLog
from .chat import ChatMessage, ChatSession, MessageCitation
from .document import AccessLevel, Document, DocumentChunk, DocumentStatus
from .evaluation import RAGEvaluationCase, RAGEvaluationRun
from .feedback import Feedback
from .ingestion import IngestionJob, IngestionJobStatus
from .price import PriceOHLC, Product, ProductCategory, ProductPrice
from .user import Role, User, UserRole

# Backward compatibility aliases (deprecated — migrate to ChatMessage)
ChatHistory = ChatMessage  # type: ignore[assignment]

__all__ = [
    "AccessLevel",
    "AuditLog",
    "ChatHistory",
    "ChatMessage",
    "ChatSession",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "Feedback",
    "IngestionJob",
    "IngestionJobStatus",
    "MessageCitation",
    "PriceOHLC",
    "Product",
    "ProductCategory",
    "ProductPrice",
    "RAGEvaluationCase",
    "RAGEvaluationRun",
    "Role",
    "User",
    "UserRole",
]
