from qdrant_client import QdrantClient as Qdrant
from qdrant_client.http.models import VectorParams, Distance

from app.config import QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION, VECTOR_SIZE


_client = None


def get_qdrant() -> Qdrant:
    global _client
    if _client is None:
        _client = Qdrant(host=QDRANT_HOST, port=QDRANT_PORT)
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
