"""Qdrant client wrapper — search, index, collection management."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from qdrant_client import QdrantClient as Qdrant
from qdrant_client.http.models import Distance, VectorParams
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from app.config import QDRANT_COLLECTION, QDRANT_HOST, QDRANT_PORT, VECTOR_SIZE
from app.models.user import ROLE_LEVEL

logger = logging.getLogger("chatbot")

_client = None


def get_qdrant() -> Qdrant:
    global _client
    if _client is None:
        _client = Qdrant(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            prefer_grpc=True,
            timeout=10,
        )
    return _client


def ensure_collection():
    client = get_qdrant()
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if QDRANT_COLLECTION not in names:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )


def get_indexed_file_names() -> list[str]:
    """Return unique file names indexed in the collection (sampled from first 1000 points)."""
    client = get_qdrant()
    file_names: set[str] = set()
    offset = None
    fetched = 0
    while fetched < 1000:
        results, next_offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in results:
            fn = p.payload.get("file_name", "")
            if fn:
                file_names.add(fn)
        fetched += len(results)
        if next_offset is None:
            break
        offset = next_offset
    return list(file_names)


_CACHED_FILE_NAMES: list[str] | None = None


ACCESS_LEVEL_RANK = {"internal": 0, "restricted": 1, "confidential": 2}


def _user_max_access_level(user_role: str | None) -> int:
    """Map user role to max access level they can see.

    viewer → 0 (internal only)
    document_admin → 1 (internal + restricted)
    system_admin → 2 (all)
    auditor → 2 (all, read-only)
    """
    if user_role is None:
        return 0
    role_max = ROLE_LEVEL.get(user_role, 0)
    if role_max >= 2:
        return 2
    if role_max >= 1:
        return 1
    return 0


def _build_filter(file_name: str, allowed_levels: list[str]) -> Filter:
    conditions = [FieldCondition(key="file_name", match=MatchValue(value=file_name))]
    if len(allowed_levels) == 1:
        conditions.append(FieldCondition(key="access_level", match=MatchValue(value=allowed_levels[0])))
    else:
        conditions.append(FieldCondition(key="access_level", match=MatchAny(any=allowed_levels)))
    return Filter(must=conditions)


def multi_source_search(
    query_vector: list[float],
    limit_per_file: int = 4,
    score_threshold: float = 0.0,
    with_vectors: bool = True,
    user_role: str | None = None,
) -> list:
    """Search across all indexed files independently and merge results.

    Filters chunks by access_level based on user_role. Viewers see only
    `internal` chunks; document_admins also see `restricted`; system_admin
    and auditor see all (including `confidential`).
    """
    global _CACHED_FILE_NAMES
    client = get_qdrant()

    if _CACHED_FILE_NAMES is None:
        _CACHED_FILE_NAMES = get_indexed_file_names()
        logger.info("multi_source_search: %d unique files indexed", len(_CACHED_FILE_NAMES))

    max_al = _user_max_access_level(user_role)
    allowed_levels = [lvl for lvl, rank in ACCESS_LEVEL_RANK.items() if rank <= max_al] or ["internal"]

    all_hits = []

    with ThreadPoolExecutor(max_workers=min(len(_CACHED_FILE_NAMES), 10) if _CACHED_FILE_NAMES else 1) as executor:
        futures = {
            executor.submit(
                client.search,
                collection_name=QDRANT_COLLECTION,
                query_vector=query_vector,
                limit=limit_per_file,
                score_threshold=score_threshold,
                query_filter=_build_filter(file_name, allowed_levels),
                with_vectors=with_vectors,
            ): file_name
            for file_name in _CACHED_FILE_NAMES
        }

        for future in as_completed(futures):
            file_name = futures[future]
            try:
                hits = future.result()
                all_hits.extend(hits)
            except Exception as exc:
                logger.warning("multi_source_search: error searching file %s: %s", file_name, exc)

    all_hits.sort(key=lambda h: h.score, reverse=True)
    return all_hits


def invalidate_file_cache() -> None:
    """Call this after a new document is ingested so the file list is refreshed."""
    global _CACHED_FILE_NAMES
    _CACHED_FILE_NAMES = None
