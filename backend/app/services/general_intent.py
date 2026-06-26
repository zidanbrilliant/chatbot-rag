"""General intent classifier — pre-LLM routing.

Returns one of:
- "casual_greeting"  → fixed response from strict_mode
- "price_query"      → delegate to intent_classifier.detect_price_intent
- "out_of_scope"     → refuse (creative/unsafe tasks)
- "rag_question"     → proceed with RAG pipeline

Ponytail: pattern-based, no LLM call. Heuristics live here, not in chat.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.strict_mode import get_casual_response

_CASUAL_KEYWORDS = {
    "halo", "hai", "hi", "hey", "hei", "assalamualaikum", "selamat",
    "apa kabar", "gimana kabar", "piye kabar", "how are you",
    "kamu siapa", "siapa kamu", "nama kamu", "kamu apa", "who are you",
    "terima kasih", "makasih", "thanks", "thank you", "matur suwun",
    "tes", "test", "coba", "testing",
}

# Out-of-scope: creative/general knowledge tasks the bot shouldn't do
_OUT_OF_SCOPE_PATTERNS = [
    re.compile(r"\b(buatkan?|tulis|lakukan|generate|create|write)\b.{0,30}\b(pantun|resep|cerpen|puisi|surat|email|skrip|lagu|story|poem|recipe|letter|essay|joke|lelucon)\b", re.IGNORECASE),
    re.compile(r"\b(gambar|draw|illustrate|render)\b", re.IGNORECASE),
    re.compile(r"\b(translate|terjemahkan)\s+(ke\s+)?(inggris|english|jepang|japanese|mandarin|china)\b", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*[\+\-\*\/x]\s*\d+\s*$"),  # bare math
    re.compile(r"\b(ignore|forget|disregard)\b.{0,30}\b(previous|prior|all|instructions?|prompt|rules?)\b", re.IGNORECASE),
    re.compile(r"\b(you\s+are\s+now|act\s+as|developer\s+mode|god\s*mode|jailbreak|bypass)\b", re.IGNORECASE),
    re.compile(r"\b(system\s*:\s*|\[system\]|<\|system\|>)", re.IGNORECASE),
]

# Price intent keywords — delegate to existing detect_price_intent if matched
_PRICE_KEYWORDS = re.compile(
    r"\b(harga|price|biaya|cost|berapa\s+(harga|biaya)|"
    r"tertinggi|terendah|terbaru|pembukaan|penutupan|"
    r"highest|lowest|latest|opening|closing|"
    r"naik|turun|konsisten|stabil|fluktuai|"
    r"per\s+(kg|gram|ton|liter|unit|pcs|buah|pack)\b)",
    re.IGNORECASE,
)


@dataclass
class IntentResult:
    intent: str  # casual_greeting | price_query | out_of_scope | rag_question
    confidence: float
    reason: str
    casual_response: str | None = None  # populated for casual_greeting


def classify_intent(query: str) -> IntentResult:
    """Classify a user query into one of four intents.

    Order of checks matters: casual first (cheapest), then out_of_scope (refuse),
    then price (delegate), else rag_question (default).
    """
    if not query or not query.strip():
        return IntentResult(
            intent="rag_question",
            confidence=0.5,
            reason="empty query — treating as rag_question",
        )

    q = query.strip().lower()

    # 1. Casual greeting — delegate to existing strict_mode logic
    # Try original query, then with trailing punctuation stripped
    for attempt in (query, q.rstrip("!.,? "), q):
        casual = get_casual_response(attempt)
        if casual is not None:
            return IntentResult(
                intent="casual_greeting",
                confidence=0.95,
                reason="matched casual greeting pattern",
                casual_response=casual,
            )

    # 2. Out-of-scope: creative tasks, math, translation, drawing
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(query):
            return IntentResult(
                intent="out_of_scope",
                confidence=0.85,
                reason=f"matched out_of_scope pattern: {pattern.pattern[:40]}",
            )

    # 3. Price intent — fast keyword pre-check before full RAG
    if _PRICE_KEYWORDS.search(query):
        return IntentResult(
            intent="price_query",
            confidence=0.90,
            reason="matched price keyword",
        )

    # 4. Default: regular RAG question
    return IntentResult(
        intent="rag_question",
        confidence=0.70,
        reason="no special pattern matched",
    )


OUT_OF_SCOPE_MESSAGE = (
    "Maaf, saya hanya dapat membantu pertanyaan terkait informasi harga produk, "
    "perbandingan harga, dan konten dokumen di knowledge base. "
    "Silakan tanyakan hal yang lebih spesifik."
)
