import logging
import os
import threading
import time
import uuid as uuid_lib
from pathlib import Path

import redis
from prometheus_fastapi_instrumentator import Instrumentator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import (
    ADMIN_RATE_LIMIT_MAX,
    CORS_ORIGINS,
    DATA_DIR,
    QDRANT_COLLECTION,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    REDIS_URL,
)
from app.database import SessionLocal, engine
from app.routers import chat, documents
from app.services.qdrant_client import ensure_collection, get_qdrant
from app.services.scheduler import start_session_cleanup
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, IngestionJobStatus
from app.core.config import get_settings
from alembic.config import Config as AlembicConfig
from alembic import command
from sqlalchemy import text
from pythonjsonlogger import jsonlogger
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

logger = logging.getLogger("chatbot")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s')
logHandler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(logHandler)
logger.addFilter(RequestIdFilter())

app = FastAPI(title="Knowledge Base Chatbot", version="1.0.0")

# Instrument Prometheus Metrics
Instrumentator().instrument(app).expose(app)

# Redis client for rate limiting
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    window_start = now - (now % RATE_LIMIT_WINDOW)
    
    max_requests = (
        ADMIN_RATE_LIMIT_MAX if request.url.path.startswith("/api/v1/documents") else RATE_LIMIT_MAX
    )
    
    redis_key = f"rate_limit:{client_ip}:{window_start}"
    try:
        current_requests = redis_client.incr(redis_key)
        if current_requests == 1:
            redis_client.expire(redis_key, RATE_LIMIT_WINDOW * 2)
            
        if current_requests > max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Terlalu banyak permintaan. Silakan coba lagi nanti."},
            )
    except Exception as e:
        logger.error("Redis rate limiter error: %s", str(e))
        # Fallback allow if redis is down
        pass

    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid_lib.uuid4()))
    request.state.request_id = req_id
    token = request_id_var.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        request_id_var.reset(token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(documents.router)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".csv", ".xlsx"}


def _validate_required_config():
    """Fail fast if critical env vars are missing."""
    settings = get_settings()
    missing = settings.validate_required()
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in the values."
        )
    logger.info("Configuration validated — %d settings loaded", len(settings.model_dump()))


def auto_ingest_data_dir():
    """Scan /data for files, create ingestion jobs for the worker to process."""
    if not os.path.isdir(DATA_DIR):
        return
    entries = [
        e for e in os.listdir(DATA_DIR)
        if os.path.isfile(os.path.join(DATA_DIR, e))
        and Path(e).suffix.lower() in ALLOWED_EXTENSIONS
        and not e.startswith("~$")
    ]
    if not entries:
        logger.info("No files to auto-ingest in %s", DATA_DIR)
        return
    logger.info("Queueing %d files for ingestion from %s", len(entries), DATA_DIR)
    for entry in entries:
        path = os.path.join(DATA_DIR, entry)
        file_size = os.path.getsize(path)
        if file_size < 50:
            continue
        db = SessionLocal()
        try:
            # Skip if already has active record (completed, queued, or processing)
            existing = (
                db.query(Document)
                .filter(
                    Document.original_filename == entry,
                    Document.status.in_([
                        DocumentStatus.COMPLETED,
                        DocumentStatus.QUEUED,
                        DocumentStatus.PROCESSING,
                    ]),
                )
                .first()
            )
            if existing:
                logger.debug("Skipped %s (existing status=%s)", entry, existing.status.value)
                continue
            ext = Path(entry).suffix.lower().lstrip(".")
            doc_id = str(uuid_lib.uuid4())
            doc = Document(
                id=doc_id,
                original_filename=entry,
                stored_filename=f"{doc_id}.{ext}",
                file_path=path,
                file_type=ext,
                size_bytes=file_size,
                status="queued",
            )
            db.add(doc)
            job = IngestionJob(document_id=doc_id, status="queued", max_attempts=3)
            db.add(job)
            db.commit()
            logger.info("Queued: %s -> doc=%s", entry, doc_id)
        except Exception as e:
            logger.error("Queue failed for %s: %s", entry, str(e)[:200])
            db.rollback()
        finally:
            db.close()


def _run_migrations():
    """Run Alembic migrations on startup."""
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    if os.path.isfile(alembic_ini):
        cfg = AlembicConfig(alembic_ini)
        command.upgrade(cfg, "head")
        logger.info("Database migrations applied successfully")
    else:
        logger.warning("alembic.ini not found — skipping migrations")

@app.on_event("startup")
def on_startup():
    _validate_required_config()
    _run_migrations()
    ensure_collection()
    # Pre-load embedding model to avoid first-query cold start
    _warmup_embedding()
    thread = threading.Thread(target=auto_ingest_data_dir, daemon=True)
    thread.start()
    start_session_cleanup()


def _warmup_embedding():
    """Call embedding API once at startup to keep model loaded in Ollama."""
    try:
        import requests as _req
        _req.post(
            f"{os.getenv('OLLAMA_BASE_URL', 'http://host.docker.internal:11434')}/api/embeddings",
            json={"model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"), "prompt": "startup warmup", "keep_alive": "10m"},
            timeout=30,
        )
        logger.info("Embedding model warmup complete")
    except Exception:
        logger.warning("Embedding warmup failed — first query may be slow")


@app.on_event("shutdown")
def on_shutdown():
    engine.dispose()
    try:
        qdrant = get_qdrant()
        qdrant.close()
    except Exception:
        pass


@app.get("/health")
def health_check():
    checks = {}
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    try:
        qdrant = get_qdrant()
        qdrant.get_collection(QDRANT_COLLECTION)
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = str(e)

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}

@app.get("/healthz/live")
def liveness_probe():
    return {"status": "alive"}

@app.get("/healthz/ready")
def readiness_probe():
    checks = {}
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    try:
        qdrant = get_qdrant()
        qdrant.get_collection(QDRANT_COLLECTION)
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = str(e)

    all_ok = all(v == "ok" for v in checks.values())
    
    if not all_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail={"status": "degraded", "checks": checks})
        
    return {"status": "ready", "checks": checks}
