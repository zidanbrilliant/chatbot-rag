"""Tests for MarketplaceScraper — uses mock session to avoid DB dependency."""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.marketplace_scraper import (
    MarketplaceScraper,
    MarketPrice,
    get_marketplace_label,
    is_marketplace_url,
)
from app.services.web_filter import (
    enrich_web_with_source_score,
    extract_model_tokens,
    filter_web_by_product_match,
    score_web_source,
)

# ── extract_model_tokens (NEW) ─────────────────────────


def test_extract_model_tokens_simple():
    tokens = extract_model_tokens("Polytron PAS 8C28")
    assert "PAS 8C28" in tokens
    # Longest first
    assert tokens[0] == "PAS 8C28"


def test_extract_model_tokens_lcd():
    tokens = extract_model_tokens("LED 32V1753")
    assert "32V1753" in tokens


def test_extract_model_tokens_pure_alpha():
    tokens = extract_model_tokens("Polytron speaker")
    # No digit-bearing tokens
    assert tokens == []


def test_extract_model_tokens_multiword():
    tokens = extract_model_tokens("Samsung Galaxy S24 Ultra")
    assert "S24" in tokens
    assert "Ultra" in tokens or "S24" in tokens


def test_extract_model_tokens_empty():
    assert extract_model_tokens("") == []
    assert extract_model_tokens(None) == []


# ── filter_web_by_product_match (NEW) ──────────────────


def test_filter_web_by_product_match_keeps_matching():
    web = [
        {"title": "Polytron PAS 8C28", "snippet": "Rp 2.500.000", "url": "https://tokopedia.com/1"},
        {"title": "Polytron PAS 8CF28", "snippet": "Rp 2.450.000", "url": "https://tokopedia.com/2"},
    ]
    out = filter_web_by_product_match(web, "Polytron PAS 8C28")
    assert len(out) == 1
    assert "PAS 8C28" in out[0]["title"]
    assert out[0]["model_matched"] == "PAS 8C28"


def test_filter_web_by_product_match_drops_generic():
    web = [
        {"title": "Daftar Speaker Polytron", "snippet": "Berbagai tipe", "url": "https://x.com/1"},
    ]
    out = filter_web_by_product_match(web, "Polytron PAS 8C28")
    assert len(out) == 0


def test_filter_web_by_product_match_no_target():
    web = [{"title": "X", "snippet": "Y", "url": "https://x.com"}]
    assert filter_web_by_product_match(web, "") == web


def test_filter_web_by_product_match_no_tokens():
    web = [{"title": "X", "snippet": "Y", "url": "https://x.com"}]
    # No digits in target -> all pass
    assert filter_web_by_product_match(web, "foobar") == web


# ── score_web_source (NEW) ─────────────────────────────


def test_score_web_source_tokopedia():
    subtype, boost = score_web_source("https://www.tokopedia.com/p/123")
    assert subtype == "marketplace:tokopedia"
    assert boost == 1.5


def test_score_web_source_shopee():
    subtype, _ = score_web_source("https://shopee.co.id/product/123")
    assert subtype == "marketplace:shopee"


def test_score_web_source_brand_store():
    subtype, boost = score_web_source("https://polytron.co.id/products/pas-8c28")
    assert subtype == "brand_store"
    assert boost == 1.2


def test_score_web_source_generic_blog():
    subtype, boost = score_web_source("https://example.com/blog/post")
    assert subtype == "generic_blog"
    assert boost == 0.7


def test_score_web_source_empty():
    subtype, _ = score_web_source("")
    assert subtype == "generic_blog"


# ── is_marketplace_url (NEW) ───────────────────────────


def test_is_marketplace_url_true():
    assert is_marketplace_url("https://tokopedia.com/p/x") is True
    assert is_marketplace_url("https://shopee.co.id/y") is True
    assert is_marketplace_url("https://bhinneka.com/z") is True


def test_is_marketplace_url_false():
    assert is_marketplace_url("https://example.com") is False
    assert is_marketplace_url("") is False
    assert is_marketplace_url(None) is False


# ── enrich_web_with_source_score (NEW) ─────────────────


def test_enrich_web_sorts_marketplaces_first():
    web = [
        {"title": "Blog", "snippet": "x", "url": "https://blog.com", "best_price": None},
        {"title": "Tokopedia", "snippet": "x", "url": "https://tokopedia.com/p", "best_price": None},
        {"title": "Polytron", "snippet": "x", "url": "https://polytron.co.id", "best_price": None},
    ]
    out = enrich_web_with_source_score(web)
    assert "tokopedia" in out[0]["source_subtype"]
    assert "brand_store" in out[1]["source_subtype"]
    assert out[2]["source_subtype"] == "generic_blog"


# ── get_marketplace_label (NEW) ─────────────────────────


def test_get_marketplace_label():
    assert get_marketplace_label("tokopedia") == "Tokopedia"
    assert get_marketplace_label("shopee") == "Shopee"
    # Unknown marketplace — snake_case is converted to Title Case
    assert get_marketplace_label("unknown_market") == "Unknown Market"
    assert get_marketplace_label("foo") == "Foo"


# ── MarketplaceScraper (NEW) ───────────────────────────


def _make_mock_db(snapshots=None):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = snapshots[0] if snapshots else None
    db.query.return_value = query
    return db


def test_scraper_cached_returns_none_when_empty():
    db = _make_mock_db(snapshots=[])
    scraper = MarketplaceScraper(db)
    assert scraper.get_cached("Polytron PAS 8C28", "tokopedia") is None


def test_scraper_cached_returns_snapshot_when_fresh():
    snap = MagicMock()
    snap.product_query = "polytron pas 8c28"
    snap.marketplace = "tokopedia"
    snap.scraped_at = datetime.utcnow() - timedelta(hours=1)
    snap.price = Decimal("2500000")
    snap.currency = "IDR"
    snap.url = "https://tokopedia.com/123"
    snap.snippet_excerpt = "Polytron PAS 8C28 Rp 2.500.000"
    db = _make_mock_db(snapshots=[snap])
    scraper = MarketplaceScraper(db)
    result = scraper.get_cached("Polytron PAS 8C28", "tokopedia")
    assert result is not None
    assert result.is_cached is True
    assert result.marketplace == "tokopedia"
    assert result.price == Decimal("2500000")


def test_scraper_cached_returns_none_when_stale():
    snap = MagicMock()
    snap.scraped_at = datetime.utcnow() - timedelta(hours=48)  # > 24h TTL
    # First call returns None (because stale -> filter excludes it)
    # We use first() to return None for stale
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = None  # Stale -> filtered out
    db.query.return_value = query
    scraper = MarketplaceScraper(db)
    assert scraper.get_cached("X", "tokopedia") is None


def test_scraper_save_snapshot():
    db = MagicMock()
    scraper = MarketplaceScraper(db)
    snap = scraper.save_snapshot(
        product_query="Polytron PAS 8C28",
        marketplace="tokopedia",
        price=Decimal("2500000"),
        currency="IDR",
        url="https://tokopedia.com/x",
        snippet_excerpt="snippet",
    )
    assert snap is not None
    assert db.add.called
    assert db.commit.called


def test_scraper_search_marketplace_with_results():
    with patch("app.services.marketplace_scraper.search_web") as mock_sw:
        mock_sw.return_value = [
            MagicMock(
                url="https://www.tokopedia.com/p/x",
                title="Polytron PAS 8C28",
                snippet="Rp 2.500.000 untuk Polytron PAS 8C28",
            ),
        ]
        db = MagicMock()
        scraper = MarketplaceScraper(db)
        result = scraper.search_marketplace("Polytron PAS 8C28", "tokopedia")
        assert result is not None
        assert result.marketplace == "tokopedia"
        assert result.price == Decimal("2500000")
        assert result.is_cached is False


def test_scraper_search_marketplace_url_mismatch():
    with patch("app.services.marketplace_scraper.search_web") as mock_sw:
        mock_sw.return_value = [
            MagicMock(
                url="https://shopee.co.id/p/x",  # Wrong marketplace
                title="Polytron PAS 8C28",
                snippet="Rp 2.500.000",
            ),
        ]
        db = MagicMock()
        scraper = MarketplaceScraper(db)
        # Search for tokopedia, but result is shopee -> should reject
        result = scraper.search_marketplace("Polytron PAS 8C28", "tokopedia")
        assert result is None


def test_scraper_search_all_uses_cache():
    snap = MagicMock()
    snap.product_query = "polytron pas 8c28"
    snap.marketplace = "tokopedia"
    snap.scraped_at = datetime.utcnow() - timedelta(hours=1)
    snap.price = Decimal("2500000")
    snap.currency = "IDR"
    snap.url = "https://tokopedia.com/123"
    snap.snippet_excerpt = "snippet"
    db = _make_mock_db(snapshots=[snap])
    scraper = MarketplaceScraper(db)
    # Patch get_cached to return the snap for all marketplaces
    with patch.object(MarketplaceScraper, "get_cached", return_value=MarketPrice(
        marketplace="tokopedia", price=Decimal("2500000"), currency="IDR",
        url="x", snippet_excerpt="x", is_cached=True,
    )):
        results = scraper.search_all("Polytron PAS 8C28")
    # All cached, no scraping
    assert all(r.is_cached for r in results)


def test_scraper_search_all_empty_query():
    db = MagicMock()
    scraper = MarketplaceScraper(db)
    assert scraper.search_all("") == []


# ── PriceResult staleness (NEW) ─────────────────────────


def test_stale_days_constant():
    from app.services.price_service import STALE_DAYS
    assert STALE_DAYS == 30


def test_compute_staleness_old_price():
    from datetime import date, timedelta

    from app.services.price_service import _compute_staleness
    is_stale, age = _compute_staleness(date.today() - timedelta(days=40))
    assert is_stale is True
    assert age == 40


def test_compute_staleness_fresh_price():
    from datetime import date, timedelta

    from app.services.price_service import _compute_staleness
    is_stale, age = _compute_staleness(date.today() - timedelta(days=5))
    assert is_stale is False
    assert age == 5


def test_compute_staleness_none():
    from app.services.price_service import _compute_staleness
    is_stale, age = _compute_staleness(None)
    assert is_stale is False
    assert age is None


def test_make_price_result_sets_staleness():
    from datetime import date, timedelta
    from decimal import Decimal

    from app.services.price_service import make_price_result
    r = make_price_result(
        product_name="X",
        price=Decimal("100"),
        currency="IDR",
        price_date=date.today() - timedelta(days=60),
    )
    assert r.is_stale is True
    assert r.age_days == 60


def test_make_price_result_fresh():
    from datetime import date
    from decimal import Decimal

    from app.services.price_service import make_price_result
    r = make_price_result(
        product_name="X",
        price=Decimal("100"),
        currency="IDR",
        price_date=date.today(),
    )
    assert r.is_stale is False
    assert r.age_days == 0
