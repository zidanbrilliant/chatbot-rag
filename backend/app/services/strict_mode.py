"""Strict Mode Classifier — determines how tightly to restrict LLM for a given query."""

from __future__ import annotations

import re

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
