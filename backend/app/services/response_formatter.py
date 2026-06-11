"""Response formatter for price queries — grouped output.

Builds hybrid output with separated internal/external sections:
- Internal: prominent hero cards with database values
- External: collapsible comparison list from web search

Each row has:
- field_label: "Tertinggi" / "Terendah" / etc.
- price: full format "Rp 1.500.000" (no abbreviation)
- date: Indonesian format "10 Jan 2025"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.intent_classifier import PriceIntent
from app.services.price_service import PriceResult

logger = logging.getLogger("chatbot")


# Indonesian month abbreviations
ID_MONTHS = [
    "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]

ID_MONTHS_FULL = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


@dataclass
class PriceCard:
    """One price row, formatted for display."""

    title: str
    product: str
    price: str            # Full format: "Rp 1.500.000"
    field_label: str      # "Tertinggi" / "Terendah" / etc.
    date: str             # "10 Jan 2025" or ""
    source_detail: str
    url: str | None = None
    type: str = "internal"
    confidence: float = 1.0
    unit: str | None = None
    field_type: str = ""
    raw_value: float = 0.0
    raw_currency: str = ""


@dataclass
class GroupedPriceTable:
    """Output: internal cards as primary, external as comparison."""

    internal_cards: list[PriceCard] = field(default_factory=list)
    external_cards: list[PriceCard] = field(default_factory=list)
    field_label: str = ""
    field_type: str = ""
    query_summary: str = ""
    intent: dict[str, Any] = field(default_factory=dict)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Flat list for frontend rendering."""
        out: list[dict[str, Any]] = []
        for c in self.internal_cards:
            out.append({
                "type": "internal",
                "title": c.title,
                "product": c.product,
                "price": c.price,
                "field_label": c.field_label,
                "field_type": c.field_type,
                "date": c.date,
                "source": c.source_detail,
                "confidence": c.confidence,
                "unit": c.unit or "-",
                "url": None,
            })
        for c in self.external_cards:
            out.append({
                "type": "external",
                "title": c.title,
                "product": c.product,
                "price": c.price,
                "field_label": c.field_label,
                "field_type": c.field_type,
                "date": c.date,
                "source": c.source_detail,
                "confidence": c.confidence,
                "unit": c.unit or "-",
                "url": c.url,
            })
        return out


def build_grouped_price_table(
    internal_results: list[PriceResult],
    web_results: list[dict[str, Any]],
    intent: PriceIntent,
) -> GroupedPriceTable:
    """Build grouped output: internal as primary, external as comparison."""
    table = GroupedPriceTable(
        field_label=intent.field_label(),
        field_type=intent.field_type,
        query_summary=_build_query_summary(intent),
        intent={
            "type": intent.query_type,
            "target": intent.target,
            "date": intent.target_date.isoformat() if intent.target_date else None,
            "date_range_start": intent.date_range_start.isoformat() if intent.date_range_start else None,
            "date_range_end": intent.date_range_end.isoformat() if intent.date_range_end else None,
            "currency": intent.currency,
            "category": intent.category,
            "field_type": intent.field_type,
            "field_label": intent.field_label(),
        },
    )

    # Build internal cards
    for r in internal_results:
        price_str = _format_price_full(r.price, r.currency)
        date_str = _format_date_id(r.price_date) if r.price_date else ""
        field_label = (
            _field_label_for(r.field_type)
            if r.field_type
            else intent.field_label()
        )
        table.internal_cards.append(
            PriceCard(
                title=r.source_detail or "Database",
                product=r.product_name,
                price=price_str,
                field_label=field_label,
                date=date_str,
                source_detail=r.source_detail,
                type="internal",
                confidence=r.relevance_score,
                unit=r.unit,
                field_type=r.field_type or intent.field_type,
                raw_value=float(r.price),
                raw_currency=r.currency,
            )
        )

    # Build external cards (from filtered web results with context_prices)
    for w in web_results:
        ctx_prices = w.get("context_prices", [])
        if not ctx_prices:
            continue
        # Take top-1 price per result
        top = ctx_prices[0]
        price_str = _format_price_full(Decimal(str(top.value)), top.currency)
        date_str = (
            _format_date_id_from_iso(top.date_context) if top.date_context else ""
        )
        field_label = _field_label_for(top.field_type) if top.field_type else ""
        table.external_cards.append(
            PriceCard(
                title=w.get("title", "")[:60],
                product=intent.target or "",
                price=price_str,
                field_label=field_label,
                date=date_str,
                source_detail=w.get("title", "")[:60],
                url=w.get("url"),
                type="external",
                confidence=top.confidence,
                field_type=top.field_type,
                raw_value=top.value,
                raw_currency=top.currency,
            )
        )

    return table


# ── Formatting helpers ──────────────────────────────────


def _format_price_full(value: Decimal | float, currency: str) -> str:
    """Full price format with proper thousands separator (no abbreviation)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    if v == int(v):
        return f"{currency} {int(v):,}"
    return f"{currency} {v:,.2f}"


def _format_date_id(d: "date") -> str:
    """Format date as Indonesian short: '10 Jan 2025'."""
    if d is None:
        return ""
    return f"{d.day} {ID_MONTHS[d.month]} {d.year}"


def _format_date_id_from_iso(iso: str) -> str:
    """Format ISO date string (or 'YYYY-Qn' / 'YYYY-MM-DD/YYYY-MM-DD') as ID."""
    if not iso:
        return ""
    if "/" in iso:
        parts = iso.split("/")
        if len(parts) == 2:
            return f"{_format_date_id_from_iso(parts[0])} – {_format_date_id_from_iso(parts[1])}"
    if "-Q" in iso:
        return iso.replace("-Q", " Q")  # "2024 Q1"
    if iso.count("-") == 2:
        try:
            y, m, d = iso.split("-")
            return f"{int(d)} {ID_MONTHS[int(m)]} {y}"
        except (ValueError, IndexError):
            pass
    return iso


def _field_label_for(field_type: str) -> str:
    labels = {
        "high": "Tertinggi",
        "low": "Terendah",
        "open": "Pembukaan",
        "close": "Penutupan",
        "latest": "Terbaru",
    }
    return labels.get(field_type, "")


def _build_query_summary(intent: PriceIntent) -> str:
    """Build human-readable summary of the query intent."""
    parts: list[str] = []
    if intent.field_label():
        parts.append(f"Harga {intent.field_label().lower()}")
    else:
        parts.append("Harga")
    if intent.target:
        parts.append(intent.target)
    if intent.target_date:
        parts.append(f"pada {_format_date_id(intent.target_date)}")
    elif intent.date_range_start and intent.date_range_end:
        if intent.date_range_start == intent.date_range_end.replace(
            day=__import__("datetime").date(
                intent.date_range_end.year,
                intent.date_range_end.month,
                1,
            ).day if False else 1
        ) if False else False:
            pass
        rs = _format_date_id(intent.date_range_start)
        re_ = _format_date_id(intent.date_range_end)
        if rs == re_:
            parts.append(f"pada {rs}")
        else:
            parts.append(f"{rs} – {re_}")
    if intent.aggregation and intent.aggregation in ("max", "min", "avg"):
        agg_id = {"max": "maksimum", "min": "minimum", "avg": "rata-rata"}[intent.aggregation]
        parts.append(f"({agg_id})")
    return " ".join(parts) if parts else "Harga"


# ── Markdown output (for LLM context) ───────────────────


def price_table_to_markdown(table: GroupedPriceTable) -> str:
    """Render table as markdown for LLM context."""
    if not table.internal_cards and not table.external_cards:
        return ""

    lines: list[str] = []
    if table.query_summary:
        lines.append(f"**{table.query_summary}**\n")
    if table.internal_cards:
        lines.append("## 📊 Data Internal\n")
        for c in table.internal_cards:
            field = f" [{c.field_label}]" if c.field_label else ""
            date = f" ({c.date})" if c.date else ""
            lines.append(
                f"- **{c.product}**{field}: {c.price}{date} "
                f"_— {c.source_detail}_"
            )
        lines.append("")
    if table.external_cards:
        lines.append("## 🌐 Pembanding Web\n")
        for c in table.external_cards:
            field = f" [{c.field_label}]" if c.field_label else ""
            date = f" ({c.date})" if c.date else ""
            lines.append(
                f"- **{c.product}**{field}: {c.price}{date} "
                f"_— {c.source_detail}_"
            )
        lines.append("")
    return "\n".join(lines)


# ── System prompt — strict anti-hallucination ───────────

PRICE_SYSTEM_PROMPT = """\
Anda adalah asisten yang membantu menjawab pertanyaan tentang HARGA produk/layanan.

ATURAN KETAT:
1. CONTEXT berisi data terstruktur. GUNAKAN ANGKA PERSIS dari CONTEXT.
2. JANGAN mengubah format angka (mis. "Rp 1.500.000" tidak boleh jadi "1,5 juta").
3. JANGAN menambah digit atau membulatkan sendiri.
4. Untuk pertanyaan "tertinggi/terendah", gunakan field yang sesuai (High/Low).
5. Setiap klaim HARUS menyebut field label dan tanggal sumber.
6. Data INTERNAL lebih otoritatif daripada data WEB.
7. Data WEB hanya sebagai "pembanding", bukan harga definitif.
8. Disclaimer SELALU di akhir jawaban.
9. JANGAN menyebut "CONTEXT", "CHUNK", atau terminologi teknis dalam jawaban.
10. Gunakan Bahasa Indonesia yang profesional dan ringkas.
"""


# Backward-compat: legacy function for old code
def build_price_table(
    internal_results: list[PriceResult],
    web_results: list[dict],
    query: str = "",
    target: str = "",
    max_internal: int = 5,
    max_web: int = 5,
):
    """Legacy function — returns PriceTable for backward compat with old tests."""
    from dataclasses import dataclass as _dc

    @_dc
    class PriceTable:
        rows: list = None
        query: str = ""
        target: str = ""

        def to_markdown(self) -> str:
            return ""

        def to_plain_text(self) -> str:
            return ""

        def to_dict_list(self) -> list[dict]:
            return []

    table = PriceTable(rows=[], query=query, target=target)
    seen: set = set()
    for r in internal_results[:max_internal]:
        key = (r.source_detail, float(r.price), r.currency)
        if key in seen:
            continue
        seen.add(key)
        table.rows.append({
            "source": r.source_detail or r.source,
            "product": r.product_name,
            "price": f"{r.currency} {float(r.price):,.0f}",
            "unit": r.unit or "-",
            "date": r.price_date.isoformat() if r.price_date else "-",
            "type": "internal",
            "url": None,
            "confidence": r.relevance_score,
            "field_type": r.field_type or "",
            "field_label": _field_label_for(r.field_type),
        })
    for w in web_results[:max_web]:
        snippet = w.get("snippet", "")
        if not snippet:
            continue
        from app.services.price_parser import extract_prices_from_snippet
        prices = extract_prices_from_snippet(snippet)
        if not prices:
            continue
        top = prices[0]
        key = (w.get("title", ""), top.value, top.currency)
        if key in seen:
            continue
        seen.add(key)
        table.rows.append({
            "source": w.get("title", "")[:50],
            "product": target or query,
            "price": f"{top.currency} {top.value:,.0f}",
            "unit": "-",
            "date": "recent",
            "type": "external",
            "url": w.get("url"),
            "confidence": top.confidence,
            "field_type": top.field_type or "",
            "field_label": _field_label_for(top.field_type),
        })
    return table
