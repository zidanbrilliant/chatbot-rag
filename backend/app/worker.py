"""Ingestion Worker — polls PostgreSQL for pending ingestion jobs.

Run standalone: python -m app.worker
Or via Docker: docker compose up worker
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

# Ensure app is on path when running as standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import DATA_DIR
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, IngestionJobStatus
from app.services.chunking import chunk_document
from app.services.document_processor import parse_document
from app.services.embedding import generate_embeddings
from app.services.qdrant_client import get_qdrant
from app.config import QDRANT_COLLECTION

# ── Config ──────────────────────────────────────────────

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))  # seconds
MAX_ATTEMPTS = int(os.getenv("WORKER_MAX_ATTEMPTS", "3"))

from pythonjsonlogger import jsonlogger

logger = logging.getLogger("chatbot.worker")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(logHandler)


# ── Ingestion logic ─────────────────────────────────────


def _batch_upsert(points: list, batch_size: int = 50):
    if not points:
        return
    qdrant = get_qdrant()
    for i in range(0, len(points), batch_size):
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points[i : i + batch_size])
    logger.info("Upserted %d points to Qdrant", len(points))


def process_job(job_id: str) -> bool:
    """Process a single ingestion job by job_id. Returns True on success."""
    db = SessionLocal()
    try:
        # Re-query within this session (objects must be session-bound)
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return False

        doc = db.query(Document).filter(Document.id == job.document_id).first()
        if not doc:
            logger.error("Job %s: document %s not found", job_id, job.document_id)
            return False

        file_path = doc.file_path
        if not os.path.isfile(file_path):
            logger.error("Job %s: file not found at %s", job_id, file_path)
            raise FileNotFoundError(file_path)

        # Update job + doc status
        job.status = IngestionJobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        doc.status = DocumentStatus.PROCESSING
        db.commit()
        db.refresh(job)
        logger.info("Job %s: processing file %s", job_id, doc.original_filename)

        # Parse
        parsed_docs = parse_document(file_path)
        chunk_dicts = chunk_document(parsed_docs)
        if not chunk_dicts:
            raise ValueError("No text extracted from document")

        # Embed
        texts = [c["text"] for c in chunk_dicts]
        embeddings = generate_embeddings(texts)

        # Upsert to Qdrant
        from qdrant_client.http.models import PointStruct

        points = []
        for i, (cdict, emb) in enumerate(zip(chunk_dicts, embeddings)):
            if emb is None or len(emb) == 0:
                continue
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": str(doc.id),
                        "file_name": doc.original_filename,
                        "content": cdict["text"],
                        "page_number": cdict.get("page_number"),
                        "row_index": i,
                    },
                )
            )

        if not points:
            raise ValueError("All chunks failed to embed")

        _batch_upsert(points)
        logger.info(
            "Job %s: ingested %d chunks from %s", job.id, len(points), doc.original_filename
        )

        # Mark complete
        job.status = IngestionJobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        doc.status = DocumentStatus.COMPLETED
        db.commit()
        return True

    except Exception as e:
        logger.error("Job %s failed: %s", job_id, str(e)[:200])
        try:
            if job:
                job.attempts += 1
                job.status = IngestionJobStatus.FAILED if job.attempts >= MAX_ATTEMPTS else IngestionJobStatus.QUEUED
                job.error_message = str(e)[:500]
                job.finished_at = datetime.now(timezone.utc)
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()
        return False
    finally:
        db.close()


# ── Polling loop ────────────────────────────────────────


def run_worker():
    """Main worker loop — polls for pending jobs."""
    logger.info("Worker started — polling every %ds", POLL_INTERVAL)

    while True:
        db = SessionLocal()
        try:
            # Fetch one pending job (oldest first)
            job = (
                db.query(IngestionJob)
                .filter(IngestionJob.status == IngestionJobStatus.QUEUED)
                .order_by(IngestionJob.created_at.asc())
                .with_for_update(skip_locked=True)
                .first()
            )

            if job:
                logger.info("Picked up job %s (doc=%s)", job.id, job.document_id)
                process_job(str(job.id))
            else:
                # No jobs — sleep
                pass

        except Exception as e:
            logger.error("Worker loop error: %s", str(e)[:200])
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()
