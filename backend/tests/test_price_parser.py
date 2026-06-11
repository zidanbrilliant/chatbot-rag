import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.price_parser import extract_prices_from_snippet


# ── IDR formats ────────────────────────────────────────


def test_rp_with_thousands_separator():
    prices = extract_prices_from_snippet("Harga Beras Rp 75.000 per 5kg")
    assert len(prices) >= 1
    assert prices[0].currency == "IDR"
    assert prices[0].value == 75000


def test_rp_with_decimals():
    prices = extract_prices_from_snippet("Total Rp 1.250.000,50")
    assert any(p.currency == "IDR" for p in prices)


def test_idr_prefix():
    prices = extract_prices_from_snippet("IDR 50000")
    assert len(prices) >= 1
    assert prices[0].value == 50000


def test_suffix_idr():
    prices = extract_prices_from_snippet("harga 75000 IDR")
    assert any(p.currency == "IDR" for p in prices)


# ── USD formats ────────────────────────────────────────


def test_usd_dollar_sign():
    prices = extract_prices_from_snippet("iPhone 15 priced at $1,299.00")
    assert any(p.currency == "USD" for p in prices)
    usd_prices = [p for p in prices if p.currency == "USD"]
    assert usd_prices[0].value == 1299.0


def test_usd_prefix():
    prices = extract_prices_from_snippet("USD 1500")
    assert any(p.value == 1500 and p.currency == "USD" for p in prices)


def test_usd_suffix():
    prices = extract_prices_from_snippet("price 500 USD")
    assert any(p.value == 500 and p.currency == "USD" for p in prices)


# ── EUR formats ────────────────────────────────────────


def test_eur():
    prices = extract_prices_from_snippet("EUR 100")
    assert any(p.currency == "EUR" for p in prices)


# ── Word forms (Indonesian) ───────────────────────────


def test_juta_form():
    prices = extract_prices_from_snippet("harganya 1.5 juta")
    assert any(p.value == 1_500_000 for p in prices)


def test_ribu_form():
    prices = extract_prices_from_snippet("harga cuma 75 ribu")
    assert any(p.value == 75_000 for p in prices)


# ── Edge cases ────────────────────────────────────────


def test_empty_snippet():
    assert extract_prices_from_snippet("") == []


def test_no_prices():
    prices = extract_prices_from_snippet("ini adalah artikel tentang Bitcoin")
    assert prices == []


def test_deduplication():
    snippet = "Rp 75.000 dan Rp 75.000 lagi"
    prices = extract_prices_from_snippet(snippet)
    idr_prices = [p for p in prices if p.currency == "IDR" and p.value == 75000]
    assert len(idr_prices) == 1


def test_sorted_by_confidence():
    snippet = "harga resmi Rp 75.000 di toko online"
    prices = extract_prices_from_snippet(snippet)
    assert len(prices) >= 1
    for i in range(len(prices) - 1):
        assert prices[i].confidence >= prices[i + 1].confidence


def test_sanity_bounds():
    prices = extract_prices_from_snippet("Rp 999999999999999999")
    for p in prices:
        assert p.value < 1e15


def test_word_count_harga_boost_confidence():
    snippet_with_harga = "harga Rp 75.000"
    snippet_without = "Rp 75.000"
    p1 = extract_prices_from_snippet(snippet_with_harga)[0]
    p2 = extract_prices_from_snippet(snippet_without)[0]
    assert p1.confidence >= p2.confidence


# ── Field context detection (NEW) ───────────────────────


def test_field_type_high_in_context():
    prices = extract_prices_from_snippet("Bitcoin highest price $50,000")
    assert any(p.field_type == "high" for p in prices)


def test_field_type_low_in_context():
    prices = extract_prices_from_snippet("harga terendah Rp 38.000.000")
    assert any(p.field_type == "low" for p in prices)


def test_field_type_open_in_context():
    prices = extract_prices_from_snippet("opening price $1,200")
    assert any(p.field_type == "open" for p in prices)


def test_field_type_close_in_context():
    prices = extract_prices_from_snippet("closing price BTC $50,000")
    assert any(p.field_type == "close" for p in prices)


def test_field_type_no_context():
    prices = extract_prices_from_snippet("Rp 75.000")
    assert all(p.field_type == "" for p in prices)


# ── Date context detection (NEW) ────────────────────────


def test_date_context_iso():
    prices = extract_prices_from_snippet("On 2024-06-15 Bitcoin was $50,000")
    assert any(p.date_context == "2024-06-15" for p in prices)


def test_date_context_dmy():
    prices = extract_prices_from_snippet("pada 15/06/2024 harga Rp 50.000")
    assert any(p.date_context == "2024-06-15" for p in prices)


def test_date_context_indonesian():
    prices = extract_prices_from_snippet("pada 15 Juni 2024 harga Rp 50.000")
    assert any(p.date_context == "2024-06-15" for p in prices)


# ── Target field/date matching (NEW) ────────────────────


def test_target_field_boost_confidence():
    snippet = "Bitcoin price $50,000"
    p_with_target = extract_prices_from_snippet(
        snippet, target_field="high"
    )[0]
    p_no_target = extract_prices_from_snippet(snippet)[0]
    # With target field set but no field detected, confidence should be lower
    assert p_with_target.confidence <= p_no_target.confidence


def test_target_field_match_boost():
    snippet = "Bitcoin highest price $50,000"
    p_with_match = extract_prices_from_snippet(
        snippet, target_field="high"
    )[0]
    p_no_target = extract_prices_from_snippet(snippet)[0]
    # Field match should boost
    assert p_with_match.confidence > p_no_target.confidence


def test_target_date_boost():
    snippet = "On 2024-06-15 Bitcoin was $50,000"
    p_match = extract_prices_from_snippet(
        snippet, target_date="2024-06-15"
    )[0]
    p_no_target = extract_prices_from_snippet(snippet)[0]
    assert p_match.confidence > p_no_target.confidence
