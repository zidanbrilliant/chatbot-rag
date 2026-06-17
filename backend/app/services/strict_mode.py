"""Strict Mode Classifier — determines how tightly to restrict LLM for a given query.

Three modes:
- strict: Price/comparison/document Q&A. KB-only, refuse creative tasks. Most restrictive.
- casual: Small talk greetings. Fixed safe responses, NO LLM call.
- normal: General knowledge base Q&A. Uses STRICT_SYSTEM_PROMPT.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("chatbot")


@dataclass
class StrictModeResult:
    mode: str  # "strict" | "casual" | "normal"
    reason: str
    is_kb_only: bool = True  # all modes are KB-only now


# ── Casual patterns ────────────────────────────────────

CASUAL_GREETING_PATTERNS = [
    re.compile(r"^(hai|halo|hi|hey|hei|assalamualaikum|selamat\s+(pagi|siang|sore|malam))[\s!.,]*$", re.IGNORECASE),
    re.compile(r"^(apa\s+kabar|gimana\s+kabar|piye\s+kabar|how\s+are\s+you)[\s?!.,]*$", re.IGNORECASE),
    re.compile(r"^(tes|test|coba|testing)[\s!.,]*$", re.IGNORECASE),
    re.compile(r"^(kamu\s+siapa|siapa\s+kamu|nama\s+kamu|kamu\s+apa|who\s+are\s+you)[\s?!.,]*$", re.IGNORECASE),
    re.compile(r"^(terima\s+kasih|makasih|thanks|thank\s+you|matur\s+suwun)[\s!.,]*$", re.IGNORECASE),
    re.compile(r"^(baik|bagus|mantap|oke|ok|okay|sip|nice|good)$", re.IGNORECASE),
]

# ── KB-only patterns (must use context) ────────────────

KB_ONLY_PATTERNS = [
    re.compile(r"\b(?:apa|bagaimana|jelaskan|terangkan|siapa|kapan|dimana|mengapa)\b", re.IGNORECASE),
    re.compile(r"\b(?:dokumen|document|file|laporan|kebijakan|policy|standard|sop)\b", re.IGNORECASE),
    re.compile(r"\b(?:berapa|harga|biaya|price|cost|nilai|kurs|tarif)\b", re.IGNORECASE),
    re.compile(r"\b(?:termurah|termahal|tertinggi|terendah|bandingkan|compare|vs\.?|versus)\b", re.IGNORECASE),
]

# ── Knowledge-base descriptive queries (NOT creative) ──

KB_DESCRIPTIVE_PATTERNS = [
    re.compile(r"\b(?:adalah|ialah|merupakan|disebut|dikenal\s+sebagai)\b", re.IGNORECASE),
    re.compile(r"\b(?:definisi|pengertian|maksud|tentang|mengenai|fungsi|kegunaan)\b", re.IGNORECASE),
    re.compile(r"\b(?:kelebihan|kekurangan|keuntungan|fitur|spesifikasi|cara\s+kerja)\b", re.IGNORECASE),
    re.compile(r"\b(?:review|ulasan|penjelasan|deskripsi)\b", re.IGNORECASE),
]


def classify_query(query: str) -> StrictModeResult:
    """Classify query into strict/casual/normal mode.

    Priority:
    1. Casual (fixed safe responses)
    2. KB-only (descriptive/informational queries — use context)
    3. normal (general — still uses strict prompt)
    """
    if not query or not query.strip():
        return StrictModeResult("normal", "empty query")

    q = query.strip()
    q_lower = q.lower()

    # Check casual first
    for pat in CASUAL_GREETING_PATTERNS:
        if pat.search(q_lower):
            return StrictModeResult("casual", "greeting or small talk")

    # Check KB-only (any informational pattern)
    kb_triggers = 0
    for pat in KB_ONLY_PATTERNS:
        if pat.search(q_lower):
            kb_triggers += 1
    for pat in KB_DESCRIPTIVE_PATTERNS:
        if pat.search(q_lower):
            kb_triggers += 1

    if kb_triggers > 0:
        return StrictModeResult("strict", f"kb-only query ({kb_triggers} triggers)")

    return StrictModeResult("normal", "general query")


# ── Fixed casual responses ────────────────────────────

CASUAL_FIXED_RESPONSES: dict[str, str] = {
    "halo": "Halo! Ada yang bisa saya bantu terkait informasi harga produk atau dokumen di knowledge base?",
    "hai": "Hai! Saya siap membantu Anda mencari informasi harga produk atau dokumen internal. Silakan tanyakan.",
    "hi": "Hi! What can I help you with? I can search for product prices and internal documents.",
    "assalamualaikum": "Wa'alaikumussalam warahmatullahi wabarakatuh. Ada yang bisa saya bantu?",
    "selamat": "Selamat {}! Ada yang bisa saya bantu terkait knowledge base atau harga produk?",
    "apa_kabar": "Saya siap membantu! Silakan tanyakan tentang harga produk atau dokumen di knowledge base.",
    "test": "Sistem knowledge base siap digunakan. Silakan tanyakan tentang konten dokumen atau harga produk.",
    "siapa_kamu": "Saya adalah asisten knowledge base yang membantu mencari informasi dari dokumen internal, membandingkan harga produk dengan marketplace, dan menjawab pertanyaan terkait data yang tersedia.",
    "terima_kasih": "Sama-sama! Ada lagi yang bisa saya bantu?",
    "default": "Saya adalah asisten knowledge base. Saya dapat membantu Anda dengan:\n- Mencari informasi dari dokumen internal\n- Membandingkan harga produk (database vs marketplace)\n- Menjawab pertanyaan tentang konten dokumen\n\nSilakan tanyakan sesuatu yang spesifik.",
}


def get_casual_response(query: str) -> str | None:
    """Get a fixed safe response for casual queries. Returns None if not casual."""
    if not query:
        return None

    q = query.strip().lower()

    if re.match(r"^(hai|halo|hi|hey|hei)$", q):
        return CASUAL_FIXED_RESPONSES["halo"]
    if re.match(r"^assalamualaikum[\s!.,]*$", q):
        return CASUAL_FIXED_RESPONSES["assalamualaikum"]
    if re.match(r"^(apa\s+kabar|gimana\s+kabar|piye\s+kabar|how\s+are\s+you)[\s?!.,]*$", q):
        return CASUAL_FIXED_RESPONSES["apa_kabar"]
    if re.match(r"^(kamu\s+siapa|siapa\s+kamu|nama\s+kamu|kamu\s+apa|who\s+are\s+you)[\s?!.,]*$", q):
        return CASUAL_FIXED_RESPONSES["siapa_kamu"]
    if re.match(r"^(terima\s+kasih|makasih|thanks|thank\s+you|matur\s+suwun)[\s!.,]*$", q):
        return CASUAL_FIXED_RESPONSES["terima_kasih"]
    if re.match(r"^(tes|test|coba|testing)[\s!.,]*$", q):
        return CASUAL_FIXED_RESPONSES["test"]
    if re.match(r"^selamat\s+(pagi|siang|sore|malam)[\s!.,]*$", q):
        import re as _re
        time_of_day = _re.search(r"(pagi|siang|sore|malam)", q)
        tod = time_of_day.group(1) if time_of_day else ""
        return CASUAL_FIXED_RESPONSES["selamat"].format(tod)

    return None
