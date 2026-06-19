"""Intent classifier for chat queries with field-level context detection.

Detects whether a user query is asking about prices. If so, extracts:
- target: what product/item
- field_type: high | low | open | close | latest
- target_date: if specific date
- date_range_start/end: if period
- currency: IDR/USD/EUR hint
- query_type: catalog | timeseries | range
- aggregation: max | min | avg (for range queries)
"""

from __future__ import annotations

import logging
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger("chatbot")


@dataclass
class PriceIntent:
    is_price_query: bool
    query_type: str = ""             # "catalog" | "timeseries" | "range" | "multi_criteria"
    field_type: str = ""             # "high" | "low" | "open" | "close" | "latest" | ""
    target: str = ""
    target_date: date | None = None
    date_range_start: date | None = None
    date_range_end: date | None = None
    currency: str = "IDR"
    min_price: float | None = None
    max_price: float | None = None
    category: str | None = None
    aggregation: str = ""           # "max" | "min" | "avg"
    has_recent_marker: bool = False # "hari ini" / "saat ini" / "sekarang" with "low" field
    attributes: dict[str, Any] | None = None
    confidence: float = 0.0

    def field_label(self) -> str:
        """Indonesian label for the field."""
        labels = {
            "high": "Tertinggi",
            "low": "Terendah",
            "open": "Pembukaan",
            "close": "Penutupan",
            "latest": "Terbaru",
        }
        return labels.get(self.field_type, "")


# ── Trigger patterns ────────────────────────────────────

PRICE_TRIGGER_PATTERNS = [
    re.compile(r"\bberapa\s+harga\b", re.IGNORECASE),
    re.compile(r"\bharga\s+(?:berapa|brp|brapa)\b", re.IGNORECASE),
    re.compile(r"^\s*harga\s+\w+", re.IGNORECASE),
    re.compile(r"\bprice\s+(?:of|for)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:biaya|tarif|ongkos|ongkir)\s+\w+", re.IGNORECASE),
    re.compile(r"\bberapa\s+(?:biaya|tarif|ongkir)\b", re.IGNORECASE),
    re.compile(r"\bkurs\s+(?:dollar|rupiah|usd|eur|sgd|jpy)\b", re.IGNORECASE),
    re.compile(r"\bnilai\s+tukar\b", re.IGNORECASE),
    re.compile(
        r"\bharga\s+(?:saham|crypto|kripto|bitcoin|btc|eth|ethereum|laptop|hp|handphone|barang|produk)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:cari|lihat|cek)\s+harga\b", re.IGNORECASE),
    re.compile(
        r"\b(?:di\s+bawah|kurang\s+dari|di\s+atas|lebih\s+dari|max|min)\s+[\d.,]+\s*(?:jt|juta|ribu|rb|k)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:antara|dari)\s+[\d.,]+\s+(?:sampai|hingga|to)\s+[\d.,]+", re.IGNORECASE),
    # NEW: OHLC-field specific triggers
    re.compile(
        r"\b(?:tertinggi|terendah|pembukaan|penutupan|terbaru|saat\s+ini|sekarang)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:high|low|open|close|latest|current)\s+(?:price|value)?\b", re.IGNORECASE),
]

# ── Field detection ─────────────────────────────────────

FIELD_PATTERNS = {
    "high": [
        re.compile(r"\btertinggi\b", re.IGNORECASE),
        re.compile(r"\bpuncak(?:nya)?\b", re.IGNORECASE),
        re.compile(r"\bpeak\b", re.IGNORECASE),
        re.compile(r"\bhighest\b", re.IGNORECASE),
        re.compile(r"\bmaksimum\b", re.IGNORECASE),
        re.compile(r"\bhigh(?:est)?\b", re.IGNORECASE),
    ],
    "low": [
        re.compile(r"\bterendah\b", re.IGNORECASE),
        re.compile(r"\bpaling\s+rendah\b", re.IGNORECASE),
        re.compile(r"\bpaling\s+murah\b", re.IGNORECASE),
        re.compile(r"\btermurah\b", re.IGNORECASE),
        re.compile(r"\bmurah\s+(?:harga|nya)\b", re.IGNORECASE),
        re.compile(r"\bdip\b", re.IGNORECASE),
        re.compile(r"\blowest\b", re.IGNORECASE),
        re.compile(r"\bminimum\b", re.IGNORECASE),
        re.compile(r"\blow(?:est)?\b", re.IGNORECASE),
    ],
    "open": [
        re.compile(r"\bpembukaan\b", re.IGNORECASE),
        re.compile(r"\bharga\s+buka\b", re.IGNORECASE),
        re.compile(r"\bopening\b", re.IGNORECASE),
        re.compile(r"\bopen(?:ing)?\b", re.IGNORECASE),
    ],
    "close": [
        re.compile(r"\bpenutupan\b", re.IGNORECASE),
        re.compile(r"\bharga\s+tutup\b", re.IGNORECASE),
        re.compile(r"\bclosing\b", re.IGNORECASE),
        re.compile(r"\bclose\b", re.IGNORECASE),
    ],
    "latest": [
        re.compile(r"\bterbaru\b", re.IGNORECASE),
        re.compile(r"\bsaat\s+ini\b", re.IGNORECASE),
        re.compile(r"\bsekarang\b", re.IGNORECASE),
        re.compile(r"\bhari\s+ini\b", re.IGNORECASE),
        re.compile(r"\blatest\b", re.IGNORECASE),
        re.compile(r"\bcurrent\b", re.IGNORECASE),
    ],
}

# ── Date / range patterns ──────────────────────────────

MONTH_MAP_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

# "tahun 2024", "year 2024"
YEAR_PATTERN = re.compile(r"\b(?:tahun|year)\s+(\d{4})\b", re.IGNORECASE)
# "Januari 2024"
MONTH_YEAR_PATTERN = re.compile(
    r"\b(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b", re.IGNORECASE
)
# "Q1 2024", "Q2 2024"
QUARTER_PATTERN = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE)
# "Januari-Maret 2024" (with dash, no space required) OR "Januari s/d Maret 2024" (with space)
MONTH_RANGE_DASH_PATTERN = re.compile(
    r"\b(" + "|".join(MONTH_MAP_ID.keys()) + r")\s*[-–—]\s*("
    + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)
MONTH_RANGE_WORD_PATTERN = re.compile(
    r"\b(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+(?:sampai|s/d|to|hingga)\s+("
    + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)

# ── Currency patterns ──────────────────────────────────

CURRENCY_PATTERNS = {
    "USD": [re.compile(r"\b(?:us\$|usd|dollar|dolar)\b", re.IGNORECASE)],
    "EUR": [re.compile(r"\b(?:eur|euro)\b", re.IGNORECASE)],
    "SGD": [re.compile(r"\b(?:sgd|singapore\s+dollar)\b", re.IGNORECASE)],
    "JPY": [re.compile(r"\b(?:jpy|yen|jepang)\b", re.IGNORECASE)],
    "IDR": [re.compile(r"\b(?:rp|rupiah|idr)\b", re.IGNORECASE)],
}

CATEGORY_KEYWORDS = {
    "crypto": ["bitcoin", "btc", "ethereum", "eth", "kripto", "crypto", "usdt"],
    "stock": ["saham", "stock", "ihsg", "idx"],
    "product": ["laptop", "hp", "handphone", "tv", "kulkas", "mesin", "mobil", "motor"],
    "material": ["bahan", "material", "baja", "semen", "cat", "kayu"],
    "service": ["jasa", "service", "servis", "biaya", "ongkir", "ongkos"],
}

UNIT_PRICE_KEYWORDS = {
    "kg": ["kg", "kilogram", "kilo"],
    "liter": ["liter", "l"],
    "pcs": ["pcs", "piece", "buah", "biji"],
    "gram": ["gram", "gr"],
    "sack": ["karung", "sak", "sack"],
    "box": ["box", "dus", "kardus"],
}

# ── Main detector ──────────────────────────────────────


def detect_price_intent(query: str) -> PriceIntent:
    """Detect if a query is a price query and extract full context."""
    if not query or not query.strip():
        return PriceIntent(is_price_query=False)

    q = query.strip()
    q_lower = q.lower()

    is_price = any(p.search(q_lower) for p in PRICE_TRIGGER_PATTERNS)
    if not is_price:
        return PriceIntent(is_price_query=False)

    target = _extract_target(q)
    field_type = _detect_field(q_lower)
    target_date = _extract_date(q_lower)
    date_range = _extract_date_range(q_lower)
    currency = _detect_currency(q_lower)
    category = _detect_category(q_lower)
    unit = _extract_unit(q_lower)
    min_p, max_p = _extract_price_range(q_lower)
    aggregation = _extract_aggregation(q_lower, field_type)
    has_recent = (
        field_type == "low"
        and _has_recent_marker(q_lower)
        and target_date is None
        and date_range is None
    )

    if min_p is not None or max_p is not None:
        qtype = "multi_criteria"
    elif date_range is not None:
        qtype = "range"
    elif target_date is not None:
        qtype = "timeseries"
    else:
        qtype = "catalog"

    intent = PriceIntent(
        is_price_query=True,
        query_type=qtype,
        field_type=field_type,
        target=target,
        target_date=target_date,
        date_range_start=date_range[0] if date_range else None,
        date_range_end=date_range[1] if date_range else None,
        currency=currency,
        min_price=min_p,
        max_price=max_p,
        category=category,
        aggregation=aggregation,
        has_recent_marker=has_recent,
        attributes={"unit": unit} if unit else None,
        confidence=0.9 if target else 0.6,
    )
    logger.info(
        "Price intent: type=%s field=%s target='%s' date=%s range=%s..%s currency=%s agg=%s",
        qtype, field_type, target[:40], target_date,
        intent.date_range_start, intent.date_range_end,
        currency, aggregation,
    )
    return intent


# ── Helpers ────────────────────────────────────────────


def _extract_target(query: str) -> str:
    """Extract product/item name from query, stripping trigger words and dates."""
    q = query.strip()

    patterns_to_strip = [
        r"^berapa\s+harga\s+",
        r"^harga\s+(?:berapa|brp|brapa)?\s*",
        r"^biaya\s+",
        r"^tarif\s+",
        r"^price\s+(?:of|for)\s+",
        r"^kurs\s+(?:dollar|rupiah|usd|eur|sgd|jpy)\s+",
        r"^harga\s+",
    ]
    target = q
    for pat in patterns_to_strip:
        target = re.sub(pat, "", target, flags=re.IGNORECASE).strip()
    target = re.sub(r"^(?:si|apa|berapa)\s+", "", target, flags=re.IGNORECASE).strip()
    target = re.sub(r"\?\s*$", "", target).strip()

    # Strip date phrases from end: "Bitcoin pada 2024-01-15" -> "Bitcoin"
    target = re.sub(
        r"\s+(?:pada|tanggal|di|tgl)\s+\d{4}-\d{1,2}-\d{1,2}\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    target = re.sub(
        r"\s+(?:pada|tanggal|di|tgl)\s+\d{1,2}[/-]\d{1,2}[/-]\d{4}\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    target = re.sub(
        r"\s+(?:pada|tanggal|di|tgl)\s+\d{1,2}\s+("
        + "|".join(MONTH_MAP_ID.keys())
        + r")\s+\d{4}\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    # Strip range phrases: "BTC tahun 2024", "BTC Januari 2024"
    target = re.sub(
        r"\s+(?:tahun|year)\s+\d{4}\s*$", "", target, flags=re.IGNORECASE
    ).strip()
    target = re.sub(
        r"\s+(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+\d{4}\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    target = re.sub(
        r"\s+Q[1-4]\s+\d{4}\s*$", "", target, flags=re.IGNORECASE
    ).strip()
    # Strip field keywords from end
    target = re.sub(
        r"\s+(?:tertinggi|terendah|pembukaan|penutupan|terbaru)\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    # Strip relative dates
    target = re.sub(
        r"\s+(?:kemarin|hari ini|minggu lalu|bulan lalu|tahun lalu)\s*$",
        "", target, flags=re.IGNORECASE,
    ).strip()
    # Strip trailing question words
    target = re.sub(
        r"\s+(?:berapa|brp|brapa|kasih|tolong|ya|deh)$",
        "", target, flags=re.IGNORECASE,
    ).strip()

    # Strip marketplace / channel names (anywhere in target)
    # Examples: "di Tokopedia", "di Shopee", "di Lazada", "di marketplace", "di pasaran", "di online"
    target = _strip_marketplace_noise(target)

    return target


MARKETPLACE_NOISE_PATTERNS = [
    r"\s+(?:di|via|melalui|dari|lewat|pada|di\s+marketplace|di\s+market)\s+"
    r"(?:tokopedia|shopee|lazada|bukalapak|bhinneka|blibli|bli-?bli|"
    r"marketplace|market|online|pasaran|onlineshop|e-?commerce)\b",
    r"\s+(?:di|via|melalui)\s+(?:toko\s+)?online\b",
    r"\s+(?:yang\s+)?ada\s+di\s+(?:tokopedia|shopee|lazada|bukalapak|bhinneka|blibli)\b",
]


def _strip_marketplace_noise(target: str) -> str:
    """Remove marketplace/channel references from target string.

    Examples:
        "Polytron PAS 8C28 di Tokopedia" -> "Polytron PAS 8C28"
        "Samsung TV di Shopee dan Lazada" -> "Samsung TV"
        "laptop di marketplace" -> "laptop"
    """
    if not target:
        return target
    out = target
    for pat in MARKETPLACE_NOISE_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE).strip()
    return out


def _detect_field(q_lower: str) -> str:
    """Detect which OHLC field is being asked about."""
    for field_name, patterns in FIELD_PATTERNS.items():
        for pat in patterns:
            if pat.search(q_lower):
                return field_name
    return ""


def _extract_date(q_lower: str) -> date | None:
    """Try to extract a specific date from the query."""
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", q_lower)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", q_lower)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTH_MAP_ID.keys()) + r")\s+(\d{4})\b", q_lower
    )
    if m:
        try:
            return date(int(m.group(3)), MONTH_MAP_ID[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    return None


def _extract_date_range(q_lower: str) -> tuple[date, date] | None:
    """Try to extract a date range from query."""
    # Quarter: "Q1 2024" -> 2024-01-01..2024-03-31
    m = QUARTER_PATTERN.search(q_lower)
    if m:
        q = int(m.group(1))
        year = int(m.group(2))
        start_month = (q - 1) * 3 + 1
        end_month = q * 3
        try:
            start = date(year, start_month, 1)
            # End of quarter
            if end_month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, end_month, monthrange(year, end_month)[1])
            return (start, end)
        except ValueError:
            pass

    # Year: "tahun 2024" -> 2024-01-01..2024-12-31
    m = YEAR_PATTERN.search(q_lower)
    if m:
        year = int(m.group(1))
        return (date(year, 1, 1), date(year, 12, 31))

    # Month range: "Januari-Maret 2024" -> 2024-01-01..2024-03-31
    m = MONTH_RANGE_DASH_PATTERN.search(q_lower)
    if m:
        try:
            start_month = MONTH_MAP_ID[m.group(1).lower()]
            end_month = MONTH_MAP_ID[m.group(2).lower()]
            year = int(m.group(3))
            start = date(year, start_month, 1)
            end = date(year, end_month, monthrange(year, end_month)[1])
            return (start, end)
        except (ValueError, KeyError):
            pass

    m = MONTH_RANGE_WORD_PATTERN.search(q_lower)
    if m:
        try:
            start_month = MONTH_MAP_ID[m.group(1).lower()]
            end_month = MONTH_MAP_ID[m.group(2).lower()]
            year = int(m.group(3))
            start = date(year, start_month, 1)
            end = date(year, end_month, monthrange(year, end_month)[1])
            return (start, end)
        except (ValueError, KeyError):
            pass

    # Single month: "Januari 2024" -> 2024-01-01..2024-01-31
    m = MONTH_YEAR_PATTERN.search(q_lower)
    if m:
        try:
            month = MONTH_MAP_ID[m.group(1).lower()]
            year = int(m.group(2))
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            return (start, end)
        except (ValueError, KeyError):
            pass

    return None


def _detect_currency(q_lower: str) -> str:
    for currency, patterns in CURRENCY_PATTERNS.items():
        for pat in patterns:
            if pat.search(q_lower):
                return currency
    return "IDR"


def _detect_category(q_lower: str) -> str | None:
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                return cat
    return None


def _extract_unit(q_lower: str) -> str | None:
    for unit, keywords in UNIT_PRICE_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{kw}\b", q_lower):
                return unit
    return None


def _extract_price_range(q_lower: str) -> tuple[float | None, float | None]:
    """Extract min/max price constraints."""
    range_patterns = [
        re.compile(
            r"(?:di\s+bawah|kurang\s+dari|max|maksimal|maximum)\s*[:\s]?\s*"
            r"(?:rp|rp\.|rupiah|idr|\$|usd)?\s*([\d.,]+)\s*(jt|juta|k|ribu)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:di\s+atas|lebih\s+dari|min|minimum|minimal|minimum)\s*[:\s]?\s*"
            r"(?:rp|rp\.|rupiah|idr|\$|usd)?\s*([\d.,]+)\s*(jt|juta|k|ribu)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:antara|dari)\s+([\d.,]+)\s*(jt|juta|k|ribu)?\s+"
            r"(?:sampai|sampai\s+dengan|hingga|to)\s+([\d.,]+)\s*(jt|juta|k|ribu)?",
            re.IGNORECASE,
        ),
    ]
    min_p: float | None = None
    max_p: float | None = None

    def _normalize(value: float, suffix: str | None) -> float:
        if not suffix:
            return value
        s = suffix.lower()
        if s in ("jt", "juta"):
            return value * 1_000_000
        if s in ("k", "ribu"):
            return value * 1_000
        return value

    for pat in range_patterns:
        m = pat.search(q_lower)
        if not m:
            continue
        groups = m.groups()
        if "bawah" in pat.pattern or "kurang" in pat.pattern or "max" in pat.pattern:
            try:
                v = float(groups[0].replace(".", "").replace(",", "."))
                max_p = _normalize(v, groups[1] if len(groups) > 1 else None)
            except (ValueError, IndexError):
                pass
        elif "atas" in pat.pattern or "lebih" in pat.pattern or "min" in pat.pattern:
            try:
                v = float(groups[0].replace(".", "").replace(",", "."))
                min_p = _normalize(v, groups[1] if len(groups) > 1 else None)
            except (ValueError, IndexError):
                pass
        elif "antara" in pat.pattern or "dari" in pat.pattern:
            try:
                v1 = float(groups[0].replace(".", "").replace(",", "."))
                v2 = float(groups[2].replace(".", "").replace(",", "."))
                min_p = _normalize(v1, groups[1] if len(groups) > 1 else None)
                max_p = _normalize(v2, groups[3] if len(groups) > 3 else None)
            except (ValueError, IndexError):
                pass
    return min_p, max_p


def _extract_aggregation(q_lower: str, field_type: str) -> str:
    """Determine aggregation for range queries (max/min/avg)."""
    if "rata-rata" in q_lower or "average" in q_lower or "avg" in q_lower:
        return "avg"
    if "tertinggi" in q_lower or "maksimum" in q_lower or "peak" in q_lower:
        return "max"
    if "terendah" in q_lower or "minimum" in q_lower or "lowest" in q_lower:
        return "min"
    # Default based on field type
    if field_type == "high":
        return "max"
    if field_type == "low":
        return "min"
    return ""


RECENT_MARKER_PATTERNS = [
    re.compile(r"\bhari\s+ini\b", re.IGNORECASE),
    re.compile(r"\bsaat\s+ini\b", re.IGNORECASE),
    re.compile(r"\bsekarang\b", re.IGNORECASE),
    re.compile(r"\bminggu\s+ini\b", re.IGNORECASE),
    re.compile(r"\b(today|now|current)\b", re.IGNORECASE),
]


def _has_recent_marker(q_lower: str) -> bool:
    return any(p.search(q_lower) for p in RECENT_MARKER_PATTERNS)
