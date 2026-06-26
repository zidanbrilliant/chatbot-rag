"""Ollama chat LLM — used when LLM_PROVIDER=ollama.

Calls Ollama's /api/chat endpoint with the same message shape and
retry pattern as groq_client.py. PII redaction is applied to context
to stay consistent with the Groq path.
"""
import json
import logging
import time
import urllib.error
import urllib.request

from app.config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL
from app.services.sanitizer import redact_pii

logger = logging.getLogger("chatbot")
MAX_RETRIES = 3
TIMEOUT_SECONDS = 90


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
            data = _post_json(url, payload, TIMEOUT_SECONDS)
            return data.get("message", {}).get("content") or ""
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            logger.warning(
                "Ollama chat attempt %d/%d failed: %s",
                attempt + 1, MAX_RETRIES, str(e)[:100],
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
    raise RuntimeError(f"Ollama chat failed after {MAX_RETRIES} attempts: {last_error}")
