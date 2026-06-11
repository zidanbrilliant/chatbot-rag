"""E2E test for OHLC context-aware price queries.

Tests against real Postgres with seeded OHLC data.
"""

import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/chatbot")

from app.database import SessionLocal
from app.services.intent_classifier import detect_price_intent
from app.services.price_service import PriceService
from app.services.response_formatter import build_grouped_price_table
from app.services.web_filter import filter_web_by_context


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def test_intent_btc_highest_2024():
    banner("E2E 1: Intent 'harga Bitcoin tertinggi tahun 2024'")
    intent = detect_price_intent("harga Bitcoin tertinggi tahun 2024")
    print(f"  field_type:        {intent.field_type}")
    print(f"  query_type:        {intent.query_type}")
    print(f"  date_range_start:  {intent.date_range_start}")
    print(f"  date_range_end:    {intent.date_range_end}")
    print(f"  aggregation:       {intent.aggregation}")
    print(f"  target:            '{intent.target}'")
    assert intent.field_type == "high"
    assert intent.date_range_start == date(2024, 1, 1)
    assert intent.date_range_end == date(2024, 12, 31)
    assert intent.aggregation == "max"
    assert intent.target == "Bitcoin"
    print("  PASS")


def test_priceservice_btc_high_2024():
    banner("E2E 2: PriceService.lookup_ohlc_by_range('Bitcoin', 2024, field='high', agg='max')")
    db = SessionLocal()
    try:
        service = PriceService(db)
        results = service.lookup_ohlc_by_range(
            "Bitcoin",
            date(2024, 1, 1), date(2024, 12, 31),
            field="high", aggregation="max",
        )
        print(f"  found {len(results)} result(s):")
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} | field={r.field_type} | date={r.price_date}")
        assert len(results) >= 1
        # Bitcoin high on 2024-12-01 was 1,080,000,000 (per seed)
        btc = next((r for r in results if "Bitcoin" in r.product_name), None)
        assert btc is not None
        assert btc.price == Decimal("1080000000")
        assert btc.field_type == "high"
        print("  PASS")
    finally:
        db.close()


def test_priceservice_btc_low_2024():
    banner("E2E 3: PriceService.lookup_ohlc_by_range('Bitcoin', 2024, field='low', agg='min')")
    db = SessionLocal()
    try:
        service = PriceService(db)
        results = service.lookup_ohlc_by_range(
            "Bitcoin",
            date(2024, 1, 1), date(2024, 12, 31),
            field="low", aggregation="min",
        )
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} | field={r.field_type} | date={r.price_date}")
        btc = next((r for r in results if "Bitcoin" in r.product_name), None)
        assert btc is not None
        # Bitcoin low on 2024-01-01 was 380,000,000
        assert btc.price == Decimal("380000000")
        assert btc.field_type == "low"
        print("  PASS")
    finally:
        db.close()


def test_priceservice_btc_ohlc_specific_date():
    banner("E2E 4: PriceService.lookup_ohlc_by_date('Bitcoin', 2024-12-01, 'close')")
    db = SessionLocal()
    try:
        service = PriceService(db)
        results = service.lookup_ohlc_by_date("Bitcoin", date(2024, 12, 1), "close")
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} | field={r.field_type} | date={r.price_date}")
        assert len(results) >= 1
        # 2024-12 close was 1,010,000,000
        btc = next((r for r in results if "Bitcoin" in r.product_name), None)
        assert btc is not None
        assert btc.price == Decimal("1010000000")
        print("  PASS")
    finally:
        db.close()


def test_grouped_format_with_intent():
    banner("E2E 5: Grouped formatter with intent='harga Bitcoin tertinggi 2024'")
    intent = detect_price_intent("harga Bitcoin tertinggi tahun 2024")
    db = SessionLocal()
    try:
        service = PriceService(db)
        internal = service.lookup_ohlc_by_range(
            "Bitcoin",
            intent.date_range_start, intent.date_range_end,
            field=intent.field_type, aggregation=intent.aggregation,
        )
        table = build_grouped_price_table(internal, [], intent)
        print(f"  internal cards: {len(table.internal_cards)}")
        print(f"  query summary:  {table.query_summary}")
        print(f"  field label:    {table.field_label}")
        for c in table.internal_cards:
            print(f"    - [{c.field_label}] {c.product}: {c.price} (date: {c.date})")
        assert len(table.internal_cards) >= 1
        assert "Tertinggi" in table.field_label
        assert "Bitcoin" in table.query_summary
        print("  PASS")
    finally:
        db.close()


def test_web_filter_strict():
    banner("E2E 6: Web strict filter for 'harga Bitcoin tertinggi'")
    intent = detect_price_intent("harga Bitcoin tertinggi")
    mock_web = [
        {"title": "High Article", "url": "https://a.com",
         "snippet": "Bitcoin mencapai highest price $108,000 pada 2024"},
        {"title": "Low Article", "url": "https://b.com",
         "snippet": "Bitcoin low price $38,000"},
        {"title": "Generic", "url": "https://c.com",
         "snippet": "Bitcoin current price $50,000"},
    ]
    filtered = filter_web_by_context(mock_web, intent)
    print(f"  filtered: {len(filtered)} of {len(mock_web)}")
    for w in filtered:
        print(f"    - {w['title']} | best_price.field_type={w['best_price'].field_type}")
    # Should keep only "High Article" (with 'highest' keyword)
    titles = [w["title"] for w in filtered]
    assert "High Article" in titles
    assert "Low Article" not in titles
    assert "Generic" not in titles
    print("  PASS")


if __name__ == "__main__":
    tests = [
        test_intent_btc_highest_2024,
        test_priceservice_btc_high_2024,
        test_priceservice_btc_low_2024,
        test_priceservice_btc_ohlc_specific_date,
        test_grouped_format_with_intent,
        test_web_filter_strict,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"  FAILED: {e}")
    print(f"\n{'=' * 70}")
    print(f"  OHLC E2E: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 70}\n")
    sys.exit(0 if failed == 0 else 1)
