import hashlib
import json
import logging

import redis

from app.config import REDIS_URL, SEARCH_CACHE_TTL

logger = logging.getLogger("chatbot")

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _cache_key(query: str) -> str:
    h = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]
    return f"web_search:{h}"


def get_cached_results(query: str) -> list[dict] | None:
    try:
        r = _get_redis()
        raw = r.get(_cache_key(query))
        if raw:
            logger.debug("Search cache hit for '%s'", query[:60])
            return json.loads(raw)
    except Exception as e:
        logger.warning("Search cache read error: %s", str(e)[:80])
    return None


def cache_search_results(query: str, results: list[dict], ttl: int | None = None) -> None:
    try:
        r = _get_redis()
        key = _cache_key(query)
        r.set(key, json.dumps(results), ex=ttl or SEARCH_CACHE_TTL)
        logger.debug("Search cache set for '%s' (TTL=%ds)", query[:60], ttl or SEARCH_CACHE_TTL)
    except Exception as e:
        logger.warning("Search cache write error: %s", str(e)[:80])
