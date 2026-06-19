import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_classifier import PriceIntent
from app.services.price_service import PriceResult
from app.services.response_formatter import (
    _format_date_id,
    build_fallback_nl,
    build_llm_context,
    build_nl_response,
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


# ── Marketplace sources (NEW) ──────────────────────────


def test_build_nl_response_with_market_prices():
    from datetime import datetime

    from app.services.marketplace_scraper import MarketPrice

    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Polytron PAS 8C28"
    )
    internal = [
        PriceResult(
            product_name="Polytron PAS 8C28",
            price=Decimal("2500000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
            price_date=date(2025, 1, 10),
        ),
    ]
    market = [
        MarketPrice(
            marketplace="tokopedia",
            price=Decimal("2150000"),
            currency="IDR",
            url="https://tokopedia.com/x",
            snippet_excerpt="Polytron PAS 8C28 Rp 2.150.000",
            scraped_at=datetime.utcnow(),
            is_cached=False,
        ),
        MarketPrice(
            marketplace="shopee",
            price=Decimal("2200000"),
            currency="IDR",
            url="https://shopee.co.id/y",
            snippet_excerpt="Polytron PAS 8C28 Rp 2.200.000",
            scraped_at=datetime.utcnow(),
            is_cached=True,
        ),
    ]
    nl = build_nl_response(internal, [], intent, market_prices=market)
    # Source IDs: 1=internal, 2=tokopedia, 3=shopee
    assert len(nl.sources) == 3
    assert nl.sources[0].source_type == "internal"
    assert nl.sources[1].source_type == "marketplace"
    assert nl.sources[1].marketplace == "tokopedia"
    assert nl.sources[2].source_type == "marketplace"
    assert nl.sources[2].marketplace == "shopee"
    # market_prices field propagated
    assert len(nl.market_prices) == 2


def test_llm_context_includes_comparison_block():
    from datetime import datetime

    from app.services.marketplace_scraper import MarketPrice

    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Polytron PAS 8C28"
    )
    internal = [
        PriceResult(
            product_name="Polytron PAS 8C28",
            price=Decimal("2500000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
            price_date=date(2025, 1, 10),
        ),
    ]
    market = [
        MarketPrice(
            marketplace="tokopedia",
            price=Decimal("2150000"),
            currency="IDR",
            url="https://tokopedia.com/x",
            snippet_excerpt="",
            scraped_at=datetime.utcnow(),
        ),
    ]
    nl = build_nl_response(internal, [], intent, market_prices=market)
    ctx = build_llm_context(nl, intent)
    assert "PERBANDINGAN HARGA" in ctx
    assert "Database" in ctx
    assert "Tokopedia" in ctx


def test_llm_context_marks_stale_internal():
    from datetime import date, timedelta

    from app.services.response_formatter import build_llm_context, build_nl_response
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="X"
    )
    internal = [
        PriceResult(
            product_name="X",
            price=Decimal("100"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-1",
            price_date=date.today() - timedelta(days=45),
            is_stale=True,
            age_days=45,
        ),
    ]
    nl = build_nl_response(internal, [], intent)
    assert nl.sources[0].is_stale is True
    assert nl.sources[0].age_days == 45
    ctx = build_llm_context(nl, intent)
    assert "STALE" in ctx or "STALE" in ctx.upper()


def test_price_prompt_has_comparison_rules():
    from app.services.response_formatter import PRICE_NL_SYSTEM_PROMPT
    assert "PERBANDINGAN" in PRICE_NL_SYSTEM_PROMPT
    # Marketplace reference
    assert "marketplace" in PRICE_NL_SYSTEM_PROMPT.lower()
    # Internal DB / stale data / age / days — any reference to data freshness
    prompt_lower = PRICE_NL_SYSTEM_PROMPT.lower()
    assert any(
        kw in prompt_lower
        for kw in ["stale", "lama", "hari lalu", "diupload", "diperbarui"]
    ), "Prompt should mention data freshness/stale concept"


def test_price_prompt_has_single_sentence_rule():
    """NEW: The prompt should encourage single-sentence focused answers."""
    from app.services.response_formatter import PRICE_NL_SYSTEM_PROMPT
    assert "SATU KALIMAT" in PRICE_NL_SYSTEM_PROMPT or "satu kalimat" in PRICE_NL_SYSTEM_PROMPT
    # Should also explicitly limit to 2-3 sources
    assert "2-3 sumber" in PRICE_NL_SYSTEM_PROMPT or "2-3" in PRICE_NL_SYSTEM_PROMPT


def test_fallback_nl_includes_marketplace():
    from datetime import datetime

    from app.services.marketplace_scraper import MarketPrice

    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Polytron PAS 8C28"
    )
    internal = [
        PriceResult(
            product_name="Polytron PAS 8C28",
            price=Decimal("2500000"),
            currency="IDR",
            source="postgres",
            source_detail="SKU-001",
            price_date=date(2025, 1, 10),
        ),
    ]
    market = [
        MarketPrice(
            marketplace="tokopedia",
            price=Decimal("2150000"),
            currency="IDR",
            url="https://tokopedia.com/x",
            snippet_excerpt="",
            scraped_at=datetime.utcnow(),
        ),
    ]
    nl = build_nl_response(internal, [], intent, market_prices=market)
    fallback = build_fallback_nl(nl, intent)
    assert "marketplace" in fallback.lower() or "pasaran" in fallback.lower()
    assert "Tokopedia" in fallback
    assert "2,500,000" in fallback or "IDR 2,500,000" in fallback
