"""Web price parser — extract numeric prices with field/date context.

Handles multiple price formats commonly found in Indonesian & English web results:
- Rp 75.000 / Rp 75.000,00 / Rp75.000 / IDR 75.000
- $1,500.00 / USD 1500 / US$ 1,500
- EUR 100 / €100
- 75.000 IDR (suffix form)
- "harga 75 ribu" / "1.5 juta"

Each extracted price carries:
- value, currency
- field_type: high | low | open | close | latest | ""
- date_context: ISO date if found in window
- confidence: 0.0-1.0 (boosted by field/date match with target)

Used by web_filter.py to enforce strict context matching.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("chatbot")


# ── Field keywords for context detection ────────────────

FIELD_CONTEXT_KEYWORDS = {
    "high": [
        r"\b(?:tertinggi|puncak|peak|highest|maximum|maksimum|high(?:est)?)\b",
    ],
    "low": [
        r"\b(?:terendah|dip|lowest|minimum|minimum|low(?:est)?)\b",
    ],
    "open": [
        r"\b(?:pembukaan|harga\s+buka|opening|opening\s+price|open(?:ing)?\s+price)\b",
    ],
    "close": [
        r"\b(?:penutupan|harga\s+tutup|closing|closing\s+price|close\s+price|close)\b",
    ],
    "latest": [
        r"\b(?:terbaru|saat\s+ini|sekarang|hari\s+ini|latest|current|today)\b",
    ],
}

# Indonesian month names
MONTH_MAP_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

# ── Patterns ────────────────────────────────────────────

PRICE_PATTERNS = [
    (
        re.compile(
            r"(?:\brp\.?|\brp)\s*([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+)"
            r"(?:\s*(?:jt|juta|ribu|k))?\b",
            re.IGNORECASE,
        ),
        "IDR",
    ),
    (
        re.compile(
            r"\bidr\s*([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+)\b", re.IGNORECASE
        ),
        "IDR",
    ),
    (
        re.compile(
            r"(?:us\$|\$)\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)(?!\s*[\d])",
            re.IGNORECASE,
        ),
        "USD",
    ),
    (
        re.compile(
            r"\busd\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\b", re.IGNORECASE
        ),
        "USD",
    ),
    (
        re.compile(
            r"(?:eur|€)\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\b", re.IGNORECASE
        ),
        "EUR",
    ),
    (
        re.compile(
            r"\b([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+)\s*(?:idr|rp|rupiah)\b",
            re.IGNORECASE,
        ),
        "IDR",
    ),
    (
        re.compile(
            r"\b([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\s*usd\b", re.IGNORECASE
        ),
        "USD",
    ),
]

WORD_FORM_PATTERNS = [
    (re.compile(r"\b([\d]+(?:[.,]\d+)?)\s*(juta|jt)\b", re.IGNORECASE), "IDR", 1_000_000),
    (re.compile(r"\b([\d]+(?:[.,]\d+)?)\s*(ribu|rb|k)\b", re.IGNORECASE), "IDR", 1_000),
]

# Date patterns for context detection
DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(?:tahun|year)\s+(\d{4})\b", re.IGNORECASE),
]


@dataclass
class ExtractedPrice:
    value: float
    currency: str
    raw_match: str
    confidence: float
    field_type: str = ""      # NEW
    date_context: str = ""    # NEW (ISO format)
    snippet_position: int = 0 # NEW (for ordering)

    def __repr__(self) -> str:
        return (
            f"ExtractedPrice({self.currency} {self.value:,.0f}, "
            f"field={self.field_type or 'any'}, date={self.date_context or 'n/a'}, "
            f"conf={self.confidence:.2f})"
        )


def extract_prices_from_snippet(
    snippet: str,
    default_currency: str = "IDR",
    target_field: str = "",
    target_date: str = "",
) -> list[ExtractedPrice]:
    """Extract all prices with field/date context from a text snippet.

    Args:
        snippet: web search result text
        default_currency: currency to assume if no prefix/suffix
        target_field: if set, prices matching this field get boosted confidence
        target_date: if set (ISO format), prices near this date get boosted

    Returns:
        List of ExtractedPrice, sorted by confidence desc
    """
    if not snippet or not snippet.strip():
        return []

    results: list[ExtractedPrice] = []
    seen: set[tuple[float, str]] = set()

    # Pattern-based extraction
    for pat, currency in PRICE_PATTERNS:
        for m in pat.finditer(snippet):
            raw = m.group(1)
            value = _normalize_number(raw)
            if value is None or value <= 0:
                continue
            if value > 1e15:
                continue
            key = (value, currency)
            if key in seen:
                continue
            seen.add(key)

            # Context window: 60 chars before/after
            ctx_start = max(0, m.start() - 60)
            ctx_end = min(len(snippet), m.end() + 30)
            context = snippet[ctx_start:ctx_end].lower()

            field_type = _detect_field_in_context(context)
            date_context = _detect_date_in_context(context)
            confidence = _compute_confidence(
                snippet, m.start(), m.end(), currency,
                field_type, date_context, target_field, target_date,
            )

            results.append(
                ExtractedPrice(
                    value=value,
                    currency=currency,
                    raw_match=m.group(0),
                    confidence=confidence,
                    field_type=field_type,
                    date_context=date_context,
                    snippet_position=m.start(),
                )
            )

    # Word-form extraction (e.g. "75 ribu")
    for pat, currency, multiplier in WORD_FORM_PATTERNS:
        for m in pat.finditer(snippet):
            raw = m.group(1)
            value = _normalize_number(raw)
            if value is None or value <= 0:
                continue
            value *= multiplier
            if value > 1e15:
                continue
            key = (value, currency)
            if key in seen:
                continue
            seen.add(key)

            ctx_start = max(0, m.start() - 60)
            ctx_end = min(len(snippet), m.end() + 30)
            context = snippet[ctx_start:ctx_end].lower()

            field_type = _detect_field_in_context(context)
            date_context = _detect_date_in_context(context)
            confidence = _compute_confidence(
                snippet, m.start(), m.end(), currency,
                field_type, date_context, target_field, target_date,
            )

            results.append(
                ExtractedPrice(
                    value=value,
                    currency=currency,
                    raw_match=m.group(0),
                    confidence=confidence,
                    field_type=field_type,
                    date_context=date_context,
                    snippet_position=m.start(),
                )
            )

    results.sort(key=lambda p: p.confidence, reverse=True)
    return results


# ── Helpers ────────────────────────────────────────────


def _normalize_number(s: str) -> float | None:
    if not s:
        return None
    s = s.strip()
    has_dot = "." in s
    has_comma = "," in s
    try:
        if has_dot and not has_comma:
            parts = s.split(".")
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]) and parts[0].isdigit():
                return float(s.replace(".", ""))
            return float(s)
        if has_comma and not has_dot:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) == 3:
                return float(s.replace(",", ""))
            return float(s.replace(",", "."))
        if has_dot and has_comma:
            if s.rfind(",") > s.rfind("."):
                return float(s.replace(".", "").replace(",", "."))
            return float(s.replace(",", ""))
        return float(s)
    except ValueError:
        return None


def _detect_field_in_context(context: str) -> str:
    """Look for high/low/open/close keywords in context window."""
    for field_name, patterns in FIELD_CONTEXT_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, context, re.IGNORECASE):
                return field_name
    return ""


def _detect_date_in_context(context: str) -> str:
    """Look for date pattern in context window. Return ISO format or empty."""
    # ISO format first (most specific)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", context)
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1900 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", context)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1900 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass

    # DD Month YYYY
    m = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b",
        context,
        re.IGNORECASE,
    )
    if m:
        try:
            day = int(m.group(1))
            month = MONTH_MAP_ID[m.group(2).lower()]
            year = int(m.group(3))
            if 1900 < year < 2100 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, KeyError):
            pass

    # Year only
    m = re.search(r"\b(?:tahun|year)\s+(\d{4})\b", context, re.IGNORECASE)
    if m:
        return f"{m.group(1)}-01-01/{m.group(1)}-12-31"

    # Quarter
    m = re.search(r"\bQ([1-4])\s+(\d{4})\b", context, re.IGNORECASE)
    if m:
        return f"{m.group(2)}-Q{m.group(1)}"

    return ""


def _compute_confidence(
    snippet: str,
    start: int,
    end: int,
    currency: str,
    field_type: str,
    date_context: str,
    target_field: str = "",
    target_date: str = "",
) -> float:
    """Score confidence based on context around the price match."""
    context_window = snippet[max(0, start - 50):min(len(snippet), end + 30)].lower()

    base = 0.6
    boost = 0.0

    if "harga" in context_window or "price" in context_window:
        boost += 0.15
    if "jual" in context_window or "sale" in context_window or "beli" in context_window:
        boost += 0.05
    if "official" in context_window or "resmi" in context_window or "toko" in context_window:
        boost += 0.05
    if currency in ("IDR", "USD", "EUR"):
        boost += 0.05

    # NEW: target field boost
    if target_field and field_type == target_field:
        boost += 0.25
    elif target_field and field_type == "":
        # No field detected, but target is set — slight penalty
        boost -= 0.05

    # NEW: target date boost
    if target_date and date_context and target_date in date_context:
        boost += 0.20
    elif target_date and date_context == "":
        boost -= 0.05

    return min(max(base + boost, 0.0), 1.0)
