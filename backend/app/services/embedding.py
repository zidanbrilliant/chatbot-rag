import requests

from app.config import EMBEDDING_MODEL, VECTOR_SIZE, OLLAMA_BASE_URL


def generate_embedding(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    return [generate_embedding(t) for t in texts]
