"""LLM Provider abstraction — supports Ollama (local) and Groq (cloud).

Switch via env LLM_PROVIDER=ollama|groq. Default: ollama.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Iterator

import requests as http_requests

logger = logging.getLogger("chatbot")


# ── Abstract base ──────────────────────────────────────


class LLMProvider(ABC):
    """Abstract LLM provider for generate, stream, rewrite, and rerank."""

    @abstractmethod
    def generate(self, system_prompt: str, context: str, history: list[dict], query: str) -> str:
        ...

    @abstractmethod
    def generate_stream(
        self, system_prompt: str, context: str, history: list[dict], query: str
    ) -> Iterator[str]:
        """Yields SSE data strings: data: {"event":"token","text":"..."}\n\n"""
        ...

    @abstractmethod
    def rewrite_query(self, query: str, history: list[dict] | str) -> str:
        ...

    @abstractmethod
    def rerank_chunks(self, query: str, chunks: list[dict]) -> list[dict]:
        ...


# ── Ollama Provider ────────────────────────────────────


class OllamaProvider(LLMProvider):
    """LLM via local Ollama /api/chat endpoint."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._chat_url = f"{self.base_url}/api/chat"

    def _call(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Non-streaming call. Falls back to Groq if Ollama unavailable."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_k": 20,
                "top_p": 0.9,
            },
        }
        for attempt in range(2):  # reduced retries — fall back faster
            try:
                resp = http_requests.post(self._chat_url, json=payload, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "") or ""
            except Exception as e:
                logger.warning("Ollama attempt %d/2 failed: %s", attempt + 1, str(e)[:80])
                if attempt < 1:
                    time.sleep(2)

        # Fallback to Groq
        logger.warning("Ollama down — falling back to Groq")
        from app.config import GROQ_API_KEY, GROQ_MODEL

        if GROQ_API_KEY:
            try:
                from groq import Groq

                client = Groq(api_key=GROQ_API_KEY, timeout=30.0)
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return completion.choices[0].message.content or ""
            except Exception as e2:
                logger.error("Groq fallback also failed: %s", str(e2)[:100])

        raise RuntimeError("LLM tidak tersedia — Ollama dan Groq gagal")

    def _call_stream(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Streaming SSE generator."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_k": 20,
                "top_p": 0.9,
            },
        }
        try:
            resp = http_requests.post(self._chat_url, json=payload, stream=True, timeout=120)
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield f'data: {json.dumps({"event": "token", "text": content})}\n\n'
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.error("Ollama stream error: %s", str(e)[:100])
            yield f'data: {json.dumps({"event": "error", "text": "Layanan AI lokal tidak tersedia."})}\n\n'

    def generate(self, system_prompt: str, context: str, history: list[dict] | str, query: str) -> str:
        messages = _build_messages(system_prompt, context, history, query)
        return self._call(messages)

    def generate_stream(
        self, system_prompt: str, context: str, history: list[dict] | str, query: str
    ) -> Iterator[str]:
        messages = _build_messages(system_prompt, context, history, query)
        yield from self._call_stream(messages)

    def rewrite_query(self, query: str, history: list[dict] | str) -> str:
        messages = _build_rewrite_messages(query, history)
        return self._call(messages, max_tokens=200, temperature=0.1)

    def rerank_chunks(self, query: str, chunks: list[dict]) -> list[dict]:
        return _rerank_via_provider(self, query, chunks)


# ── Groq Provider (delegates to existing groq_client internals) ──


class GroqProvider(LLMProvider):
    """LLM via Groq Cloud API."""

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def _groq_client(self):
        from groq import Groq

        return Groq(api_key=self.api_key, timeout=30.0)

    def generate(self, system_prompt: str, context: str, history: list[dict] | str, query: str) -> str:
        from app.services.groq_client import generate_response as _gen

        return _gen(system_prompt, context, history, query)

    def generate_stream(
        self, system_prompt: str, context: str, history: list[dict] | str, query: str
    ) -> Iterator[str]:
        from app.services.groq_client import generate_response_stream as _gen_stream

        yield from _gen_stream(system_prompt, context, history, query)

    def rewrite_query(self, query: str, history: list[dict] | str) -> str:
        from app.services.groq_client import rewrite_query as _rw

        return _rw(query, history)

    def rerank_chunks(self, query: str, chunks: list[dict]) -> list[dict]:
        from app.services.groq_client import rerank_chunks as _rr

        return _rr(query, chunks)


# ── Factory ─────────────────────────────────────────────


_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """Return singleton LLM provider based on LLM_PROVIDER env var."""
    global _provider
    if _provider is not None:
        return _provider

    from app.config import GROQ_API_KEY, GROQ_MODEL, LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_LLM_MODEL

    provider_name = LLM_PROVIDER.lower()
    if provider_name == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY tidak diset — tidak bisa pakai Groq provider")
        _provider = GroqProvider(model=GROQ_MODEL, api_key=GROQ_API_KEY)
        logger.info("LLM provider: Groq (model=%s)", GROQ_MODEL)
    else:
        _provider = OllamaProvider(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL)
        logger.info("LLM provider: Ollama (model=%s, url=%s)", OLLAMA_LLM_MODEL, OLLAMA_BASE_URL)

    return _provider


# ── Shared helpers ──────────────────────────────────────


def _build_messages(
    system_prompt: str, context: str, history: list[dict] | str, query: str
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        if isinstance(history, str):
            messages.append({"role": "user", "content": f"Previous conversation:\n{history}"})
        else:
            for h in history:
                messages.append({"role": h["role"], "content": h["content"]})
    if context:
        messages.append({"role": "user", "content": f"CONTEXT:\n{context}"})
    messages.append({"role": "user", "content": query})
    return messages


def _build_rewrite_messages(query: str, history: list[dict] | str) -> list[dict]:
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "Kamu adalah query rewriter. Ubah pertanyaan follow-up menjadi pertanyaan mandiri "
                "berdasarkan riwayat percakapan. JANGAN menambah fakta baru. "
                "Jawab HANYA pertanyaan yang sudah di-rewrite, tidak perlu penjelasan."
            ),
        }
    ]
    if history:
        if isinstance(history, str):
            messages.append(
                {"role": "user", "content": f"Riwayat:\n{history}\n\nPertanyaan: {query}"}
            )
        else:
            history_text = "\n".join(
                [f"{h['role']}: {h['content']}" for h in history[-10:]]
            )
            messages.append(
                {"role": "user", "content": f"Riwayat:\n{history_text}\n\nPertanyaan: {query}"}
            )
    else:
        messages.append({"role": "user", "content": query})
    return messages


def _rerank_via_provider(provider: LLMProvider, query: str, chunks: list[dict]) -> list[dict]:
    """Shared rerank logic using provider's generate."""
    if not chunks:
        return chunks

    items_text = "\n\n".join(
        f"[{i + 1}] {c.get('file_name', '')}: {str(c.get('content', ''))[:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        "Kamu adalah filter relevansi dokumen. Berikut adalah daftar potongan dokumen "
        "dan sebuah pertanyaan user. Tentukan potongan mana yang RELEVAN untuk menjawab "
        "pertanyaan.\n\n"
        f"Pertanyaan: {query}\n\n"
        f"Potongan dokumen:\n{items_text}\n\n"
        "Balas dengan daftar nomor potongan yang relevan, dipisah koma. "
        "Contoh: 1, 3, 5\n"
        "Jika tidak ada yang relevan, balas: 0"
    )
    messages = [
        {"role": "system", "content": "Kamu adalah filter relevansi yang efisien. Balas singkat."},
        {"role": "user", "content": prompt},
    ]
    try:
        # Use a simple non-streaming call
        reply = provider._call(messages, max_tokens=100, temperature=0.0)  # type: ignore[union-attr]
    except Exception:
        logger.warning("Reranking failed via provider")
        return chunks

    reply = reply.strip()
    if reply == "0" or not reply:
        logger.info("Rerank via provider: LLM determined no chunks are relevant")
        return []
    indices = [int(x.strip()) - 1 for x in re.split(r"[,;]", reply) if x.strip().isdigit()]
    relevant = [chunks[i] for i in indices if 0 <= i < len(chunks)]

    if not relevant:
        logger.info("Rerank via provider: no valid indices, returning empty")
        return []
    logger.info("Rerank: %d/%d chunks relevant", len(relevant), len(chunks))
    return relevant


# ── Public API — same interface as groq_client.py ────────

# Re-export utility functions from groq_client (provider-agnostic)
from app.services.groq_client import (  # noqa: E402, F401
    expand_synonyms,
    format_context,
    format_context_with_ids,
    insert_citations,
    is_citation_valid,
    validate_citations,
)


def generate_response(system_prompt: str, context: str, history: list[dict] | str, query: str) -> str:
    return get_llm().generate(system_prompt, context, history, query)


def generate_response_stream(
    system_prompt: str, context: str, history: list[dict] | str, query: str
) -> Iterator[str]:
    yield from get_llm().generate_stream(system_prompt, context, history, query)


def rewrite_query(query: str, history: list[dict] | str) -> str:
    return get_llm().rewrite_query(query, history)


def rerank_chunks(query: str, chunks: list[dict]) -> list[dict]:
    return get_llm().rerank_chunks(query, chunks)
