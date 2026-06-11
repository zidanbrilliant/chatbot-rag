import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_classifier import PriceIntent
from app.services.price_parser import extract_prices_from_snippet
from app.services.web_filter import filter_web_by_context, relax_filter


def test_strict_filter_drops_no_field_match():
    """If target_field=high, results without 'high/low/etc' keyword are dropped."""
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Bitcoin",
        field_type="high",
    )
    web = [
        {
            "title": "Web 1",
            "url": "https://x.com",
            "snippet": "Bitcoin price $50,000 today",  # no field keyword
        },
    ]
    filtered = filter_web_by_context(web, intent)
    assert filtered == []


def test_strict_filter_keeps_matching_field():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Bitcoin",
        field_type="high",
    )
    web = [
        {
            "title": "Web 1",
            "url": "https://x.com",
            "snippet": "Bitcoin highest price $108,000",  # has 'highest'
        },
    ]
    filtered = filter_web_by_context(web, intent)
    assert len(filtered) == 1
    assert filtered[0]["best_price"].field_type == "high"


def test_strict_filter_drops_no_date_match():
    """If target_date set, results without matching date are dropped."""
    intent = PriceIntent(
        is_price_query=True, query_type="timeseries", target="Bitcoin",
        target_date=__import__("datetime").date(2024, 6, 15),
    )
    web = [
        {
            "title": "Web 1",
            "url": "https://x.com",
            "snippet": "Bitcoin price $50,000 on 2024-01-01",  # different date
        },
    ]
    filtered = filter_web_by_context(web, intent)
    assert filtered == []


def test_strict_filter_keeps_matching_date():
    intent = PriceIntent(
        is_price_query=True, query_type="timeseries", target="Bitcoin",
        target_date=__import__("datetime").date(2024, 6, 15),
    )
    web = [
        {
            "title": "Web 1",
            "url": "https://x.com",
            "snippet": "Bitcoin on 2024-06-15 was $50,000",
        },
    ]
    filtered = filter_web_by_context(web, intent)
    assert len(filtered) == 1


def test_no_intent_field_passes_all():
    """If no field_type set, all results pass through."""
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Bitcoin",
    )
    web = [
        {"title": "W1", "url": "https://x.com", "snippet": "Bitcoin $50,000"},
        {"title": "W2", "url": "https://y.com", "snippet": "Bitcoin $51,000"},
    ]
    filtered = filter_web_by_context(web, intent)
    assert len(filtered) == 2


def test_relax_filter_includes_unmatched():
    """Relax filter keeps all results with prices, just without strict match."""
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Bitcoin",
        field_type="high",
    )
    web = [
        {"title": "W1", "url": "https://x.com", "snippet": "Bitcoin $50,000"},
    ]
    relaxed = relax_filter(web, intent)
    assert len(relaxed) == 1


def test_empty_web_returns_empty():
    intent = PriceIntent(is_price_query=True, query_type="catalog")
    assert filter_web_by_context([], intent) == []
    assert relax_filter([], intent) == []


def test_web_results_enriched_with_context_prices():
    intent = PriceIntent(
        is_price_query=True, query_type="catalog", target="Bitcoin",
        field_type="high",
    )
    web = [
        {
            "title": "W1",
            "url": "https://x.com",
            "snippet": "Bitcoin highest $108,000",
        },
    ]
    filtered = filter_web_by_context(web, intent)
    assert "context_prices" in filtered[0]
    assert "best_price" in filtered[0]
    assert filtered[0]["best_price"].field_type == "high"
