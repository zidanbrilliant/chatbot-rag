import logging
import os
import time

import redis
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pythonjsonlogger import jsonlogger
from sqlalchemy import text

from alembic import command
from app.config import (
    CORS_ORIGINS,
    QDRANT_COLLECTION,
    RATE_LIMIT_ADMIN_MAX,
    RATE_LIMIT_CHAT_MAX,
    RATE_LIMIT_WINDOW,
    REDIS_URL,
)
from app.database import SessionLocal, engine
from app.routers import chat, documents
from app.services.qdrant_client import ensure_collection, get_qdrant
from app.services.scheduler import start_session_cleanup

logger = logging.getLogger("chatbot")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(logHandler)

app = FastAPI(title="Knowledge Base Chatbot", version="1.0.0")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    window_start = now - (now % RATE_LIMIT_WINDOW)

    max_requests = (
        RATE_LIMIT_ADMIN_MAX if request.url.path.startswith("/api/v1/documents") else RATE_LIMIT_CHAT_MAX
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

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(documents.router)


def _run_migrations():
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    if os.path.isfile(alembic_ini):
        cfg = AlembicConfig(alembic_ini)
        command.upgrade(cfg, "head")
        logger.info("Database migrations applied successfully")
    else:
        logger.warning("alembic.ini not found — skipping migrations")


@app.on_event("startup")
def on_startup():
    _run_migrations()
    ensure_collection()
    start_session_cleanup()


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
