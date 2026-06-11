import os
import sys
from decimal import Decimal
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_classifier import PriceIntent
from app.services.price_service import PriceResult
from app.services.response_formatter import (
    build_nl_response,
    build_llm_context,
    build_fallback_nl,
    _format_date_id,
)


# ── build_nl_response ──────────────────────────────────


def test_empty_internal_no_web():
    intent = PriceIntent(is_price_query=True, query_type="catalog", target="X")
    nl = build_nl_response([], [], intent)
    assert nl.sources == []


def test_only_internal_results():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog",
        target="Beras Premium 5kg", field_type="latest",
    )
    internal = [
        PriceResult(
            product_name="Beras Premium 5kg",
            price=Decimal("75000"),
            currency="IDR",
            unit="5kg",
            source="postgres",
            source_detail="SKU-001",
            price_date=date(2025, 1, 10),
            field_type="latest",
        )
    ]
    nl = build_nl_response(internal, [], intent)
    assert len(nl.sources) == 1
    assert nl.sources[0].source_type == "internal"
    assert "Beras" in nl.sources[0].label or "Beras" in nl.sources[0].snippet
    assert nl.sources[0].price == "IDR 75,000"


def test_internal_external_in_source_list():
    """Internal gets IDs 1,2,3... External continues from there."""
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="iPhone"
    )
    internal = [
        PriceResult(
            product_name="iPhone 15 Pro",
            price=Decimal("15000000"),
            currency="IDR",
            source="postgres",
            source_detail="APL-IP15P",
        ),
    ]
    web = [
        {
            "title": "Tokopedia",
            "url": "https://tokopedia.link/x",
            "snippet": "harga iPhone 15 Pro Rp 15.500.000",
            "best_price": type("P", (), {
                "value": 15_500_000.0, "currency": "IDR",
                "field_type": "", "date_context": "",
                "confidence": 0.7, "raw_match": "Rp 15.500.000",
            })(),
        },
    ]
    nl = build_nl_response(internal, web, intent)
    assert len(nl.sources) == 2
    assert nl.sources[0].source_id == 1
    assert nl.sources[0].source_type == "internal"
    assert nl.sources[1].source_id == 2
    assert nl.sources[1].source_type == "external"


# ── LLM context with [N] markers ───────────────────────


def test_llm_context_has_citation_markers():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Beras"
    )
    internal = [
        PriceResult(
            product_name="Beras Premium 5kg",
            price=Decimal("75000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
        ),
    ]
    nl = build_nl_response(internal, [], intent)
    context = build_llm_context(nl, intent)
    assert "[1]" in context
    assert "SKU-001" in context or "Beras" in context


def test_llm_context_strict_rules():
    """Context must contain anti-hallucination instructions."""
    intent = PriceIntent(is_price_query=True, query_type="catalog")
    nl = build_nl_response([], [], intent)
    context = build_llm_context(nl, intent)
    assert "JANGAN" in context or "tidak ditemukan" in context.lower()


# ── Fallback NL builder ────────────────────────────────


def test_fallback_nl_with_internal_only():
    intent = PriceIntent(is_price_query=True, query_type="catalog", target="Beras")
    internal = [
        PriceResult(
            product_name="Beras Premium 5kg",
            price=Decimal("75000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
        ),
    ]
    nl = build_nl_response(internal, [], intent)
    fallback = build_fallback_nl(nl, intent)
    assert "Beras" in fallback
    assert "75,000" in fallback
    assert "[1]" in fallback
    assert "dapat berubah" in fallback.lower()


def test_fallback_nl_with_comparison():
    intent = PriceIntent(is_price_query=True, query_type="catalog", target="Beras")
    internal = [
        PriceResult(
            product_name="Beras Premium 5kg",
            price=Decimal("75000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
        ),
    ]
    web = [
        {
            "title": "Tokopedia",
            "url": "https://tokopedia.link/x",
            "snippet": "Beras Rp 78.000",
            "best_price": type("P", (), {
                "value": 78000.0, "currency": "IDR",
                "field_type": "", "date_context": "",
                "confidence": 0.6, "raw_match": "Rp 78.000",
            })(),
        },
    ]
    nl = build_nl_response(internal, web, intent)
    fallback = build_fallback_nl(nl, intent)
    assert "Database" in fallback or "internal" in fallback.lower()
    assert "online" in fallback.lower() or "web" in fallback.lower()
    assert "Perbandingan" in fallback


def test_fallback_nl_empty_sources():
    intent = PriceIntent(is_price_query=True, query_type="catalog")
    nl = build_nl_response([], [], intent)
    fallback = build_fallback_nl(nl, intent)
    assert "tidak ditemukan" in fallback.lower()


# ── Date format (Indonesian) ───────────────────────────


def test_date_format_indonesian():
    d = date(2024, 6, 15)
    formatted = _format_date_id(d)
    assert formatted == "15 Jun 2024"


def test_date_format_january():
    assert _format_date_id(date(2025, 1, 10)) == "10 Jan 2025"


def test_date_format_december():
    assert _format_date_id(date(2024, 12, 31)) == "31 Des 2024"


# ── Source dict for frontend ──────────────────────────


def test_source_to_dict():
    intent = PriceIntent(is_price_query=True, query_type="catalog", target="Beras")
    internal = [
        PriceResult(
            product_name="Beras Premium 5kg",
            price=Decimal("75000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
            price_date=date(2025, 1, 10),
        ),
    ]
    nl = build_nl_response(internal, [], intent)
    src_dict = nl.sources[0].to_dict()
    assert "id" in src_dict
    assert "label" in src_dict
    assert "type" in src_dict
    assert "price" in src_dict
    assert src_dict["price_date"] == "2025-01-10"
