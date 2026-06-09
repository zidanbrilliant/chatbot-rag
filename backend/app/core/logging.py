import json
import logging
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        return json.dumps(log_entry)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())

logger = logging.getLogger("chatbot")
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_interaction(
    query: str, confidence: float | None, source: str, session_id: str | None = None
):
    logger.info(
        "Interaction logged",
        extra={
            "query": query,
            "confidence": confidence,
            "source": source,
            "session_id": session_id,
            "event": "interaction",
        },
    )
