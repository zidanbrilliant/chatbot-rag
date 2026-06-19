"""Ollama chat LLM — used when LLM_PROVIDER=ollama.

Calls Ollama's /api/chat endpoint with the same message shape and
retry pattern as groq_client.py. PII redaction is applied to context
to stay consistent with the Groq path.
"""
import logging
import time

import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL
from app.services.sanitizer import redact_pii

logger = logging.getLogger("chatbot")
MAX_RETRIES = 3
TIMEOUT_SECONDS = 90


def generate_response_ollama(system_prompt: str, context: str, history: str, query: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.append({"role": "user", "content": f"Previous conversation:\n{history}"})
    if context:
        messages.append({"role": "user", "content": f"Reference context:\n{redact_pii(context)}"})
    messages.append({"role": "user", "content": query})

    payload = {"model": OLLAMA_CHAT_MODEL, "messages": messages, "stream": False}
    url = f"{OLLAMA_BASE_URL}/api/chat"
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()["message"]["content"] or ""
        except (requests.RequestException, KeyError, ValueError) as e:
            last_error = e
            logger.warning(
                "Ollama chat attempt %d/%d failed: %s",
                attempt + 1, MAX_RETRIES, str(e)[:100],
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
    raise RuntimeError(f"Ollama chat failed after {MAX_RETRIES} attempts: {last_error}")
