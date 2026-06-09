import logging
import threading
import time
from datetime import datetime, timedelta

from app.config import SESSION_CLEANUP_INTERVAL, SESSION_TIMEOUT_MINUTES
from app.database import SessionLocal
from app.models.chat import ChatSession

logger = logging.getLogger("chatbot")


def cleanup_expired_sessions():
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        expired = db.query(ChatSession).filter(ChatSession.updated_at < cutoff).all()
        if expired:
            for session in expired:
                db.delete(session)
            db.commit()
            logger.info("Cleaned up %d expired sessions", len(expired))
        else:
            logger.debug("No expired sessions to clean up")
    except Exception as e:
        db.rollback()
        logger.error("Session cleanup failed: %s", str(e))
    finally:
        db.close()


def _cleanup_loop():
    while True:
        time.sleep(SESSION_CLEANUP_INTERVAL)
        cleanup_expired_sessions()


def start_session_cleanup():
    thread = threading.Thread(target=_cleanup_loop, daemon=True)
    thread.start()
    logger.info("Session cleanup scheduler started (interval=%ds)", SESSION_CLEANUP_INTERVAL)
