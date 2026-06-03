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


import concurrent.futures

def generate_embeddings(texts: list[str]) -> list[list[float]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        return list(executor.map(generate_embedding, texts))
