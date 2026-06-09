import functools
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError

from app.config import EMBEDDING_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger("chatbot")
MAX_RETRIES = 4
EMBEDDING_CONCURRENCY = 4


def _generate_single(text: str) -> list[float]:
    last_error = None
    payload = json.dumps({"model": EMBEDDING_MODEL, "prompt": text, "keep_alive": "10m"}).encode()
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json", "Connection": "close"},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["embedding"]
        except Exception as e:
            last_error = e
            backoff = min(2 ** attempt, 8)
            logger.warning(
                "Embed attempt %d/%d failed (%d chars, retry in %ds): %s",
                attempt + 1, MAX_RETRIES, len(text), backoff, str(e)[:80],
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
    raise last_error


@functools.lru_cache(maxsize=1000)
def _cached_single(text: str) -> list[float]:
    return _generate_single(text)


def generate_embedding(text: str) -> list[float]:
    return _cached_single(text)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=EMBEDDING_CONCURRENCY) as executor:
        futures = {executor.submit(_generate_single, t): i for i, t in enumerate(texts)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error(
                    "Embedding chunk %d/%d failed (%d chars): %s",
                    idx + 1,
                    len(texts),
                    len(texts[idx]),
                    str(e)[:100],
                )
                results[idx] = []
    return results
