import logging
import uuid
from pathlib import Path

from qdrant_client.http.models import PointStruct
from sqlalchemy.orm import Session

from app.config import QDRANT_COLLECTION
from app.models.document import Document
from app.services.chunking import chunk_document
from app.services.document_processor import parse_document
from app.services.embedding import generate_embeddings
from app.services.qdrant_client import get_qdrant, invalidate_file_cache

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
    if not points:
        return
    qdrant = get_qdrant()
    for i in range(0, len(points), batch_size):
        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points[i : i + batch_size],
        )


def ingest_file(file_path: str, file_name: str, file_size: int, db: Session) -> str:
    existing = db.query(Document).filter(Document.original_filename == file_name).first()
    if existing and _has_vectors_in_qdrant(existing.id):
        return str(existing.id)

    if existing:
        db.delete(existing)
        db.commit()

    doc_id = str(uuid.uuid4())
    ext = Path(file_path).suffix.lower().lstrip(".")
    file_type = ext if ext in ("pdf", "docx", "csv", "xlsx") else "unknown"
    db_doc = Document(
        id=doc_id,
        original_filename=file_name,
        stored_filename=f"{doc_id}.{file_type}",
        file_path=file_path,
        file_type=file_type,
        size_bytes=file_size,
        status="processing",
    )
    db.add(db_doc)
    db.commit()

    try:
        text = parse_document(file_path)
        raw_chunks = chunk_document([{"text": text, "page_number": None}])
        chunks = [c["text"] for c in raw_chunks]

        if not chunks:
            db_doc.status = "failed"
            db.commit()
            raise ValueError("No text extracted")

        embeddings = generate_embeddings(chunks)

        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
            if emb is None or len(emb) == 0:
                continue
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": doc_id,
                        "file_name": file_name,
                        "content": chunk,
                        "page_number": None,
                        "row_index": i,
                    },
                )
            )

        _batch_upsert(points)

        if not points:
            db_doc.status = "failed"
            db.commit()
            raise ValueError("All chunks failed to embed")
        elif len(points) < len(chunks):
            logger.warning(
                "Partial ingestion: name=%s, embedded=%d/%d chunks",
                file_name,
                len(points),
                len(chunks),
            )

        db_doc.status = "completed"
        db.commit()
        invalidate_file_cache()  # refresh cached file list so multi_source_search finds new file
        logger.info("Document ingested: name=%s, id=%s, chunks=%d", file_name, doc_id, len(points))
        return doc_id

    except Exception as e:
        db_doc.status = "failed"
        db.commit()
        logger.error("Ingestion failed: name=%s, error=%s", file_name, str(e))
        raise
