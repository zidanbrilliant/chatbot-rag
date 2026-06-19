import html
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Security, UploadFile
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import ADMIN_API_KEY, DATA_DIR, MAX_FILE_SIZE_MB, QDRANT_COLLECTION
from app.database import get_db
from app.models.document import Document
from app.models.ingestion import IngestionJob
from app.schemas.document import DeleteResponse, DocumentOut, UploadResponse
from app.services.qdrant_client import get_qdrant

logger = logging.getLogger("chatbot")

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".csv", ".xlsx"}
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILENAME_LENGTH = 255

_ALLOWED_FILENAME_RE = re.compile(r"^[a-zA-Z0-9 _.\-()\[\]+,@&=;]+$")


def _sanitize_filename(filename: str) -> str:
    name = html.escape(filename[:MAX_FILENAME_LENGTH])
    name = re.sub(r'[<>"\'\\/\x00-\x1f]', "_", name)
    return name


api_key_header = APIKeyHeader(name="X-API-Key")

def verify_admin_key(api_key: str = Security(api_key_header)):
    if api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key


def _validate_magic_bytes(contents: bytes, ext: str) -> bool:
    if not contents:
        return False
    if ext == ".pdf":
        return contents.startswith(b"%PDF-")
    elif ext in (".docx", ".xlsx"):
        # ZIP signature
        return contents.startswith(b"PK\x03\x04") or contents.startswith(b"PK\x05\x06") or contents.startswith(b"PK\x07\x08")
    elif ext == ".csv":
        try:
            contents[:1024].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


@router.post("/upload", status_code=202, response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_key)
):
    raw_filename = file.filename or "unnamed"
    safe_filename = _sanitize_filename(raw_filename)
    ext = Path(raw_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not allowed. Use: {ALLOWED_EXTENSIONS}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, f"File exceeds {MAX_FILE_SIZE_MB} MB limit")
        
    if not _validate_magic_bytes(contents, ext):
        raise HTTPException(400, "File content does not match extension (invalid magic bytes)")

    doc_id = str(uuid.uuid4())
    file_path = os.path.join(DATA_DIR, f"{doc_id}{ext}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(contents)

    file_type = ext.lstrip(".")
    doc = Document(
        id=doc_id,
        original_filename=safe_filename,
        stored_filename=f"{doc_id}{ext}",
        file_path=file_path,
        file_type=file_type,
        size_bytes=len(contents),
        status="queued",
    )
    db.add(doc)

    job = IngestionJob(
        document_id=doc_id,
        status="queued",
        max_attempts=3,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info("Upload: doc=%s file=%s queued as job=%s", doc_id, safe_filename, job.id)
    return UploadResponse(document_id=doc_id, job_id=str(job.id), message="Upload berhasil. Ingestion sedang diproses.")


@router.get("", response_model=dict)
def list_documents(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    api_key: str = Depends(verify_admin_key),
):
    total = db.query(Document).count()
    docs = (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "data": [DocumentOut.from_orm(d) for d in docs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(
    document_id: str, 
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_key),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    qdrant = get_qdrant()
    offset = None
    while True:
        scroll_page, next_offset = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter={"must": [{"key": "document_id", "match": {"value": document_id}}]},
            limit=100,
            offset=offset,
        )
        point_ids = [p.id for p in scroll_page]
        if point_ids:
            qdrant.delete(collection_name=QDRANT_COLLECTION, points_selector=point_ids)
        if next_offset is None:
            break
        offset = next_offset

    db.delete(doc)
    db.commit()
    return DeleteResponse(message="Dokumen dan vektor terkait berhasil dihapus.")
