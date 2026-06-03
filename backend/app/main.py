import os
import logging
import re
import html
from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DATA_DIR, CORS_ORIGINS
from app.database import engine, Base, SessionLocal
from app.routers import chat, documents
from app.services.qdrant_client import ensure_collection
from app.services.ingestion import ingest_file

logger = logging.getLogger("chatbot")

app = FastAPI(title="Knowledge Base Chatbot", version="1.0.0")

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


def auto_ingest_data_dir():
    if not os.path.isdir(DATA_DIR):
        return
    db = SessionLocal()
    try:
        for entry in os.listdir(DATA_DIR):
            path = os.path.join(DATA_DIR, entry)
            if not os.path.isfile(path):
                continue
            ext = Path(entry).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            file_size = os.path.getsize(path)
            doc_id = ingest_file(path, entry, file_size, db)
            if doc_id:
                logger.info("Auto-ingested: %s -> %s", entry, doc_id)
    except Exception as e:
        logger.error("Auto-ingestion error: %s", str(e))
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_collection()
    thread = threading.Thread(target=auto_ingest_data_dir, daemon=True)
    thread.start()
