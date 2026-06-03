import uuid
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentOut, UploadResponse, DeleteResponse
from app.services.ingestion import ingest_file
from app.services.qdrant_client import get_qdrant
from app.config import MAX_FILE_SIZE_MB, DATA_DIR, QDRANT_COLLECTION

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".csv", ".xlsx"}
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("/upload", status_code=202, response_model=UploadResponse)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not allowed. Use: {ALLOWED_EXTENSIONS}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, f"File exceeds {MAX_FILE_SIZE_MB} MB limit")

    doc_id = str(uuid.uuid4())
    file_path = os.path.join(DATA_DIR, f"{doc_id}{ext}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(contents)

    def background_ingest():
        bg_db = SessionLocal()
        try:
            ingest_file(file_path, file.filename, len(contents), bg_db)
        finally:
            bg_db.close()

    background_tasks.add_task(background_ingest)
    return UploadResponse(document_id=doc_id, message="Upload berhasil. Ingestion sedang diproses.")


@router.get("", response_model=dict)
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return {"data": [DocumentOut.from_orm(d) for d in docs]}


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    qdrant = get_qdrant()
    scroll = qdrant.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter={"must": [{"key": "document_id", "match": {"value": document_id}}]},
        limit=100,
    )
    point_ids = [p.id for p in scroll[0]]
    if point_ids:
        qdrant.delete(collection_name=QDRANT_COLLECTION, points_selector=point_ids)

    db.delete(doc)
    db.commit()
    return DeleteResponse(message="Dokumen dan vektor terkait berhasil dihapus.")
