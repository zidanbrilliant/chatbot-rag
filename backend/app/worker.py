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
from app.models.document import AccessLevel, Document, DocumentStatus
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


# ── Auto-scan /data folder ───────────────────────────────


def _calculate_file_hash(file_path: str) -> str:
    """SHA256 hash of file contents."""
    import hashlib
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _ingest_csv_as_products(file_path: str, db) -> int:
    """Parse product CSV and insert into products + product_prices tables.

    Returns number of products inserted/updated.
    """
    try:
        from app.services.csv_product_mapper import parse_product_csv
        from app.models.price import Product, ProductPrice
    except ImportError:
        logger.warning("csv_product_mapper not available")
        return 0

    try:
        products = parse_product_csv(file_path)
    except Exception as e:
        logger.error("Failed to parse product CSV %s: %s", file_path, e)
        return 0

    inserted = 0
    for p in products:
        existing = db.query(Product).filter(Product.sku == p.sku).first()
        if existing:
            existing.name = p.name
            existing.brand = p.brand or existing.brand
            existing.category = p.category
            existing.unit = "unit"
            existing.attributes = {"tipe": p.tipe, "source_file": Path(file_path).name}
            existing.source = "csv"
        else:
            product = Product(
                sku=p.sku,
                name=p.name,
                category=p.category,
                unit="unit",
                attributes={"tipe": p.tipe, "source_file": Path(file_path).name},
                source="csv",
            )
            db.add(product)
            db.flush()

        # Insert/update product price (latest)
        if existing:
            latest = (
                db.query(ProductPrice)
                .filter(ProductPrice.product_id == existing.id)
                .order_by(ProductPrice.price_date.desc())
                .first()
            )
            product_id = existing.id
        else:
            latest = None
            product_id = product.id

        if p.price and (not latest or latest.price != p.price):
            db.add(ProductPrice(
                product_id=product_id,
                price=p.price,
                currency="IDR",
                price_date=datetime.now(timezone.utc).date(),
                supplier=Path(file_path).stem,
                source="csv",
                notes=f"imported from {Path(file_path).name}",
            ))

        inserted += 1

    db.commit()
    logger.info("Imported %d products from %s", inserted, Path(file_path).name)
    return inserted


def auto_scan_data_folder() -> int:
    """Scan /data folder, queue ingestion jobs for new files, ingest CSV products.

    For CSV product catalogs (Barang/Brand/Tipe/Harga schema):
    - Parse and import to products + product_prices tables directly
    - Mark document as COMPLETED (no vector embedding needed — products are queryable directly)
    - Store ingestion metadata in document.attributes JSONB

    For PDF/DOCX/XLSX:
    - Queue embedding + chunking job as normal

    Returns number of new jobs queued.
    """
    from app.models.document import Document

    if not os.path.isdir(DATA_DIR):
        logger.warning("DATA_DIR does not exist: %s", DATA_DIR)
        return 0

    queued = 0
    db = SessionLocal()
    try:
        for entry in os.listdir(DATA_DIR):
            path = os.path.join(DATA_DIR, entry)
            if not os.path.isfile(path):
                continue
            ext = Path(entry).suffix.lower()
            if ext not in (".pdf", ".docx", ".csv", ".xlsx"):
                continue

            try:
                file_hash = _calculate_file_hash(path)
            except Exception as e:
                logger.warning("Cannot hash %s: %s", entry, e)
                continue

            existing = (
                db.query(Document)
                .filter(Document.document_hash == file_hash)
                .first()
            )

            # ── CSV product catalog: import to products table, mark COMPLETED ──
            if ext == ".csv":
                if existing and existing.status == DocumentStatus.COMPLETED:
                    # Already done — skip
                    continue
                if existing and existing.status == DocumentStatus.FAILED and existing.attributes and existing.attributes.get("csv_products_imported"):
                    # Already imported products even though doc marked failed (e.g., old runs)
                    # Mark as completed
                    existing.status = DocumentStatus.COMPLETED
                    db.commit()
                    continue

                # First-time processing OR retry of failed CSV
                doc_id = existing.id if existing else str(uuid.uuid4())
                if not existing:
                    doc = Document(
                        id=doc_id,
                        original_filename=entry,
                        stored_filename=f"{doc_id}{ext}",
                        file_path=path,
                        file_type=ext.lstrip("."),
                        size_bytes=os.path.getsize(path),
                        document_hash=file_hash,
                        access_level=AccessLevel.INTERNAL,
                        status=DocumentStatus.PROCESSING,
                    )
                    db.add(doc)
                    db.commit()
                else:
                    existing.status = DocumentStatus.PROCESSING
                    db.commit()

                products_imported = _ingest_csv_as_products(path, db)

                if products_imported > 0:
                    # Mark as COMPLETED — no vector embedding needed
                    target_doc = existing or doc
                    target_doc.status = DocumentStatus.COMPLETED
                    target_doc.attributes = {
                        "csv_products_imported": True,
                        "products_count": products_imported,
                        "ingestion_type": "csv_catalog",
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    }
                    db.commit()
                    logger.info(
                        "CSV catalog ingested: %s — %d products (skipped vector embedding)",
                        entry, products_imported,
                    )
                else:
                    # CSV failed to parse — mark as failed
                    target_doc = existing or doc
                    target_doc.status = DocumentStatus.FAILED
                    target_doc.error_code = "CSV_PARSE_FAILED"
                    target_doc.error_message = "Failed to parse CSV — check format"
                    db.commit()
                    logger.warning("CSV catalog failed to parse: %s", entry)
                continue

            # ── Non-CSV (PDF/DOCX/XLSX): queue embedding job ──
            if existing and existing.status == DocumentStatus.COMPLETED:
                continue
            if existing and existing.status == DocumentStatus.FAILED:
                # Don't re-create a failed document — keep its history
                logger.info(
                    "Skipping %s — already failed. Reset manually if needed.",
                    entry,
                )
                continue

            doc_id = str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                original_filename=entry,
                stored_filename=f"{doc_id}{ext}",
                file_path=path,
                file_type=ext.lstrip("."),
                size_bytes=os.path.getsize(path),
                document_hash=file_hash,
                access_level=AccessLevel.INTERNAL,
                status=DocumentStatus.QUEUED,
            )
            db.add(doc)

            job = IngestionJob(
                document_id=doc_id,
                status=IngestionJobStatus.QUEUED,
                max_attempts=MAX_ATTEMPTS,
            )
            db.add(job)
            db.commit()
            queued += 1
            logger.info("Auto-ingest queued: %s (hash=%s)", entry, file_hash[:8])
    finally:
        db.close()

    if queued:
        logger.info("Auto-scan queued %d new file(s)", queued)
    return queued


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
                # Smart retry: only retry if failure is NOT due to persistent external issues
                # (like Ollama unreachable). After MAX_ATTEMPTS, mark as FAILED permanently.
                job.status = IngestionJobStatus.FAILED if job.attempts >= MAX_ATTEMPTS else IngestionJobStatus.QUEUED
                job.error_message = str(e)[:500]
                job.finished_at = datetime.now(timezone.utc)
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(e)[:500]
                # If embedding failure persists, document stays FAILED but
                # worker won't retry indefinitely (max_attempts bounds it)
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

    # Auto-scan /data on startup
    try:
        queued = auto_scan_data_folder()
        if queued:
            logger.info("Initial auto-scan queued %d file(s) for ingestion", queued)
    except Exception as e:
        logger.error("Initial auto-scan failed: %s", str(e)[:200])

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
                db.commit()  # Release FOR UPDATE lock before process_job opens its own session
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
