"""End-to-end integration test for price lookup feature.

Tests the full pipeline:
1. Intent detection
2. PriceService lookup against real Postgres
3. Response formatter
4. Mock web search for hybrid output
"""

import os
import sys
from decimal import Decimal
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.services.intent_classifier import detect_price_intent
from app.services.price_service import PriceService
from app.services.response_formatter import build_price_table
from app.services.price_parser import extract_prices_from_snippet


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def test_intent_catalog():
    banner("TEST 1: Intent detection — catalog query")
    intent = detect_price_intent("berapa harga Beras Premium 5kg")
    print(f"  is_price_query: {intent.is_price_query}")
    print(f"  query_type:     {intent.query_type}")
    print(f"  target:         '{intent.target}'")
    print(f"  currency:       {intent.currency}")
    print(f"  category:       {intent.category}")
    assert intent.is_price_query
    assert intent.query_type == "catalog"
    assert "Beras" in intent.target
    print("  PASS")


def test_intent_timeseries():
    banner("TEST 2: Intent detection — timeseries query")
    intent = detect_price_intent("harga Bitcoin pada 2024-01-15")
    print(f"  is_price_query: {intent.is_price_query}")
    print(f"  query_type:     {intent.query_type}")
    print(f"  target:         '{intent.target}'")
    print(f"  target_date:    {intent.target_date}")
    assert intent.is_price_query
    assert intent.query_type == "timeseries"
    assert intent.target_date == date(2024, 1, 15)
    print("  PASS")


def test_intent_multi_criteria():
    banner("TEST 3: Intent detection — multi-criteria query")
    intent = detect_price_intent("laptop Dell di bawah 20 juta")
    print(f"  is_price_query: {intent.is_price_query}")
    print(f"  query_type:     {intent.query_type}")
    print(f"  max_price:      {intent.max_price}")
    assert intent.is_price_query
    assert intent.query_type == "multi_criteria"
    assert intent.max_price == 20_000_000
    print("  PASS")


def test_intent_non_price():
    banner("TEST 4: Intent detection — non-price query (must NOT trigger)")
    intent = detect_price_intent("apa itu Bitcoin?")
    print(f"  is_price_query: {intent.is_price_query}")
    assert not intent.is_price_query
    print("  PASS (correctly not a price query)")


def test_priceservice_lookup_beras():
    banner("TEST 5: PriceService.lookup_by_name('Beras')")
    db = SessionLocal()
    try:
        service = PriceService(db)
        results = service.lookup_by_name("Beras")
        print(f"  found {len(results)} product(s):")
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} | source={r.source} | sku={r.source_detail}")
        assert len(results) >= 1
        assert any("Beras" in r.product_name for r in results)
        print("  PASS")
    finally:
        db.close()


def test_priceservice_lookup_btc_by_date():
    banner("TEST 6: PriceService.lookup_by_date('Bitcoin', 2024-01-01)")
    db = SessionLocal()
    try:
        service = PriceService(db)
        # Seed has Bitcoin OHLC for 2024-01-01, so use that date
        results = service.lookup_by_date("Bitcoin", date(2024, 1, 1))
        print(f"  found {len(results)} result(s):")
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} on {r.price_date}")
        assert len(results) >= 1
        assert any("Bitcoin" in r.product_name for r in results)
        assert any(r.price_date == date(2024, 1, 1) for r in results)
        print("  PASS")
    finally:
        db.close()


def test_priceservice_lookup_samsung():
    banner("TEST 7: PriceService.lookup_by_name('Samsung')")
    db = SessionLocal()
    try:
        service = PriceService(db)
        results = service.lookup_by_name("Samsung")
        print(f"  found {len(results)} product(s):")
        for r in results:
            print(f"    - {r.product_name} | {r.currency} {r.price:,.0f} | date={r.price_date}")
        assert len(results) >= 1
        assert any("Samsung" in r.product_name for r in results)
        print("  PASS")
    finally:
        db.close()


def test_web_parser_idr():
    banner("TEST 8: Web price parser — IDR formats")
    snippets = [
        "Harga iPhone 15 Pro Rp 15.500.000 di Tokopedia",
        "Total Rp 1.250.000,50",
        "Cuma 75 ribu",
        "1.5 juta untuk paket ini",
    ]
    for s in snippets:
        prices = extract_prices_from_snippet(s)
        print(f"  '{s[:50]}'")
        for p in prices:
            print(f"    -> {p.currency} {p.value:,.0f} (conf={p.confidence:.2f}, match='{p.raw_match}')")
    print("  PASS")


def test_web_parser_usd():
    banner("TEST 9: Web price parser — USD formats")
    snippets = [
        "iPhone 15 priced at $1,299.00",
        "USD 1500",
        "Bitcoin at $42,500",
    ]
    for s in snippets:
        prices = extract_prices_from_snippet(s)
        print(f"  '{s[:50]}'")
        for p in prices:
            print(f"    -> {p.currency} {p.value:,.2f} (conf={p.confidence:.2f}, match='{p.raw_match}')")
    print("  PASS")


def test_full_pipeline_hybrid():
    banner("TEST 10: Full hybrid pipeline (Postgres + mock web)")
    db = SessionLocal()
    try:
        intent = detect_price_intent("berapa harga Beras Premium 5kg")
        service = PriceService(db)
        internal = service.lookup_by_name(intent.target)

        # Mock web results
        mock_web = [
            {
                "title": "Tokopedia - Beras Premium 5kg",
                "url": "https://tokopedia.link/beras",
                "snippet": "Beras Premium 5kg Rp 78.000 stok ready",
            },
            {
                "title": "Shopee - Beras Pandan Wangi",
                "url": "https://shopee.co.id/beras",
                "snippet": "harga 1.5 juta untuk 1 karung",
            },
        ]

        table = build_price_table(internal, mock_web, query="berapa harga Beras", target="Beras")

        print(f"  internal: {len(internal)} rows")
        print(f"  web:      {len(mock_web)} results")
        print(f"  table:    {len(table.rows)} rows")
        print()
        print("  Markdown output:")
        for line in table.to_markdown().split("\n"):
            print(f"    {line}")
        print()
        print("  Plain text output:")
        for line in table.to_plain_text().split("\n"):
            print(f"    {line}")
        print()
        print("  Dict output (frontend metadata):")
        for d in table.to_dict_list():
            print(f"    {d}")
        assert len(table.rows) >= 1
        print("  PASS")
    finally:
        db.close()


def test_intent_crypto_category():
    banner("TEST 11: Intent — crypto category detection")
    intent = detect_price_intent("harga Bitcoin hari ini")
    print(f"  target:   '{intent.target}'")
    print(f"  category: {intent.category}")
    assert intent.category == "crypto"
    print("  PASS")


def test_priceservice_all_products():
    banner("TEST 12: List all seeded products (sanity check)")
    db = SessionLocal()
    try:
        from app.models.price import Product
        products = db.query(Product).all()
        print(f"  Total products: {len(products)}")
        # Show only first 10 to keep output small
        for p in products[:10]:
            latest = p.latest_price()
            price_str = f"{latest.currency} {latest.price:,.0f}" if latest else "no price"
            print(f"    - [{p.sku}] {p.name} | {price_str} | {p.unit} | {p.category}")
        if len(products) > 10:
            print(f"    ... and {len(products) - 10} more")
        # After barang.csv auto-ingest, expect >= 7 seeded + auto-imported
        # Use a lower bound so test is stable across data additions
        assert len(products) >= 7, f"Expected >= 7 products, got {len(products)}"
        print("  PASS")
    finally:
        db.close()


if __name__ == "__main__":
    tests = [
        test_intent_catalog,
        test_intent_timeseries,
        test_intent_multi_criteria,
        test_intent_non_price,
        test_intent_crypto_category,
        test_priceservice_lookup_beras,
        test_priceservice_lookup_btc_by_date,
        test_priceservice_lookup_samsung,
        test_priceservice_all_products,
        test_web_parser_idr,
        test_web_parser_usd,
        test_full_pipeline_hybrid,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 70}\n")
    sys.exit(0 if failed == 0 else 1)
