import os
import sys
from decimal import Decimal
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_classifier import PriceIntent
from app.services.price_service import PriceResult
from app.services.response_formatter import (
    build_grouped_price_table,
    price_table_to_markdown,
    _format_price_full,
    _format_date_id,
)


# ── Empty cases ────────────────────────────────────────


def test_empty_internal_no_web():
    intent = PriceIntent(is_price_query=True, query_type="catalog", target="X")
    table = build_grouped_price_table([], [], intent)
    assert table.internal_cards == []
    assert table.external_cards == []
    assert price_table_to_markdown(table) == ""


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
    table = build_grouped_price_table(internal, [], intent)
    assert len(table.internal_cards) == 1
    assert "Beras" in table.internal_cards[0].product
    assert "IDR" in table.internal_cards[0].price
    assert "75,000" in table.internal_cards[0].price
    assert table.internal_cards[0].type == "internal"


# ── Grouping ───────────────────────────────────────────


def test_internal_external_separated():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="iPhone"
    )
    internal = [
        PriceResult(
            product_name="iPhone 15 Pro",
            price=Decimal("15000000"),
            currency="IDR",
            unit="pcs",
            source="postgres",
            source_detail="APL-IP15P",
        ),
    ]
    web = [
        {
            "title": "Tokopedia",
            "url": "https://tokopedia.link/x",
            "snippet": "harga iPhone 15 Pro Rp 15.500.000",
            "context_prices": [
                type("P", (), {
                    "value": 15_500_000.0, "currency": "IDR",
                    "field_type": "", "date_context": "",
                    "confidence": 0.7, "raw_match": "Rp 15.500.000",
                })()
            ],
            "best_price": type("P", (), {
                "value": 15_500_000.0, "currency": "IDR",
                "field_type": "", "date_context": "",
                "confidence": 0.7, "raw_match": "Rp 15.500.000",
            })(),
        },
    ]
    table = build_grouped_price_table(internal, web, intent)
    assert len(table.internal_cards) == 1
    assert len(table.external_cards) == 1
    assert table.internal_cards[0].type == "internal"
    assert table.external_cards[0].type == "external"


# ── Field labels ───────────────────────────────────────


def test_field_label_high():
    intent = PriceIntent(
        is_price_query=True, query_type="range", target="Bitcoin",
        field_type="high",
    )
    internal = [
        PriceResult(
            product_name="Bitcoin",
            price=Decimal("1080000000"),
            currency="IDR",
            source="postgres_ohlc",
            source_detail="BTC | MAX high 2024-01-01..2024-12-31",
            price_date=date(2024, 12, 1),
            field_type="high",
        ),
    ]
    table = build_grouped_price_table(internal, [], intent)
    assert table.internal_cards[0].field_label == "Tertinggi"
    assert table.field_label == "Tertinggi"


def test_field_label_low():
    intent = PriceIntent(
        is_price_query=True, query_type="range", target="Bitcoin",
        field_type="low",
    )
    internal = [
        PriceResult(
            product_name="Bitcoin",
            price=Decimal("380000000"),
            currency="IDR",
            source="postgres_ohlc",
            source_detail="BTC | MIN low 2024-01-01..2024-12-31",
            price_date=date(2024, 1, 1),
            field_type="low",
        ),
    ]
    table = build_grouped_price_table(internal, [], intent)
    assert table.internal_cards[0].field_label == "Terendah"


# ── Date format (Indonesian) ───────────────────────────


def test_date_format_indonesian():
    d = date(2024, 6, 15)
    formatted = _format_date_id(d)
    assert formatted == "15 Jun 2024"


def test_date_format_january():
    assert _format_date_id(date(2025, 1, 10)) == "10 Jan 2025"


def test_date_format_december():
    assert _format_date_id(date(2024, 12, 31)) == "31 Des 2024"


# ── Price format (full, no abbreviation) ───────────────


def test_price_format_full_idr():
    assert _format_price_full(75000, "IDR") == "IDR 75,000"


def test_price_format_full_usd():
    assert _format_price_full(1500, "USD") == "USD 1,500"


def test_price_format_full_large():
    assert _format_price_full(1500000000, "IDR") == "IDR 1,500,000,000"


def test_price_format_full_decimal():
    result = _format_price_full(1250.50, "USD")
    assert "USD" in result
    assert "1,250.50" in result


# ── Markdown output ───────────────────────────────────


def test_markdown_includes_internal_section():
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
    table = build_grouped_price_table(internal, [], intent)
    md = price_table_to_markdown(table)
    assert "Data Internal" in md
    assert "Beras" in md
    assert "SKU-001" in md


def test_markdown_includes_external_section():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Beras"
    )
    web = [
        {
            "title": "Tokopedia - Beras",
            "url": "https://tokopedia.link/beras",
            "snippet": "Beras Rp 78.000",
            "context_prices": [
                type("P", (), {
                    "value": 78000.0, "currency": "IDR",
                    "field_type": "", "date_context": "",
                    "confidence": 0.6, "raw_match": "Rp 78.000",
                })()
            ],
            "best_price": type("P", (), {
                "value": 78000.0, "currency": "IDR",
                "field_type": "", "date_context": "",
                "confidence": 0.6, "raw_match": "Rp 78.000",
            })(),
        },
    ]
    table = build_grouped_price_table([], web, intent)
    md = price_table_to_markdown(table)
    assert "Pembanding Web" in md
    assert "Tokopedia" in md


def test_markdown_includes_query_summary():
    intent = PriceIntent(
        is_price_query=True, query_type="range", target="Bitcoin",
        field_type="high",
        date_range_start=date(2024, 1, 1),
        date_range_end=date(2024, 12, 31),
    )
    internal = [
        PriceResult(
            product_name="Bitcoin",
            price=Decimal("1080000000"),
            currency="IDR",
            source="postgres_ohlc",
            source_detail="BTC",
            field_type="high",
        ),
    ]
    table = build_grouped_price_table(internal, [], intent)
    md = price_table_to_markdown(table)
    # Should have summary
    assert "Tertinggi" in md or "Bitcoin" in md


# ── Dict list for frontend ─────────────────────────────


def test_dict_list_structure():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="A"
    )
    internal = [
        PriceResult(
            product_name="A", price=Decimal("100"), currency="IDR",
            source="postgres", source_detail="sku-a", field_type="latest",
        ),
    ]
    web = [
        {
            "title": "Web",
            "url": "https://x.com",
            "snippet": "harga Rp 200.000",
            "context_prices": [
                type("P", (), {
                    "value": 200000.0, "currency": "IDR",
                    "field_type": "", "date_context": "",
                    "confidence": 0.6, "raw_match": "Rp 200.000",
                })()
            ],
            "best_price": type("P", (), {
                "value": 200000.0, "currency": "IDR",
                "field_type": "", "date_context": "",
                "confidence": 0.6, "raw_match": "Rp 200.000",
            })(),
        },
    ]
    table = build_grouped_price_table(internal, web, intent)
    dicts = table.to_dict_list()
    assert len(dicts) == 2
    # Internal comes first
    assert dicts[0]["type"] == "internal"
    assert dicts[1]["type"] == "external"
    # All have required fields
    for d in dicts:
        assert "source" in d
        assert "product" in d
        assert "price" in d
        assert "field_label" in d
        assert "field_type" in d
        assert "date" in d


# ── Intent metadata ────────────────────────────────────


def test_intent_metadata_field_type():
    intent = PriceIntent(
        is_price_query=True, query_type="range", target="Bitcoin",
        field_type="high",
        date_range_start=date(2024, 1, 1),
        date_range_end=date(2024, 12, 31),
    )
    table = build_grouped_price_table([], [], intent)
    assert table.intent["field_type"] == "high"
    assert table.intent["field_label"] == "Tertinggi"
    assert table.intent["date_range_start"] == "2024-01-01"
    assert table.intent["date_range_end"] == "2024-12-31"
