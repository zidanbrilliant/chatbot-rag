import uuid
import logging

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.services.document_processor import parse_document
from app.services.chunking import chunk_text
from app.services.embedding import generate_embeddings
from qdrant_client.http.models import PointStruct

from app.services.qdrant_client import get_qdrant
from app.config import QDRANT_COLLECTION

logger = logging.getLogger("chatbot")


def _has_vectors_in_qdrant(document_id: str) -> bool:
    try:
        qdrant = get_qdrant()
        scroll = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter={"must": [{"key": "document_id", "match": {"value": document_id}}]},
            limit=1,
        )
        return len(scroll[0]) > 0
    except Exception:
        return False


def _batch_upsert(points: list[PointStruct], batch_size: int = 50):
    qdrant = get_qdrant()
    for i in range(0, len(points), batch_size):
        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points[i:i + batch_size],
        )


def ingest_file(file_path: str, file_name: str, file_size: int, db: Session) -> str:
    existing = db.query(Document).filter(Document.file_name == file_name).first()
    if existing and _has_vectors_in_qdrant(existing.id):
        return existing.id

    if existing:
        db.delete(existing)
        db.commit()

    doc_id = str(uuid.uuid4())
    db_doc = Document(id=doc_id, file_name=file_name, file_size=file_size, status=DocumentStatus.PROCESSING)
    db.add(db_doc)
    db.commit()

    try:
        text = parse_document(file_path)
        chunks = chunk_text(text)

        if not chunks:
            db_doc.status = DocumentStatus.FAILED
            db.commit()
            raise ValueError("No text extracted")

        embeddings = generate_embeddings(chunks)

        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "chunk_id": str(uuid.uuid4()),
                    "document_id": doc_id,
                    "file_name": file_name,
                    "content": chunk,
                    "page_number": None,
                    "row_index": i,
                }
            ))

        _batch_upsert(points)
        db_doc.status = DocumentStatus.INDEXED
        db.commit()
        logger.info("Document ingested: name=%s, id=%s, chunks=%d", file_name, doc_id, len(chunks))
        return doc_id

    except Exception as e:
        db_doc.status = DocumentStatus.FAILED
        db.commit()
        logger.error("Ingestion failed: name=%s, error=%s", file_name, str(e))
        raise
