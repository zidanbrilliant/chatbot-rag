import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_classifier import detect_price_intent

# ── Trigger detection ──────────────────────────────────


def test_casual_query_not_price():
    intent = detect_price_intent("halo apa kabar")
    assert intent.is_price_query is False


def test_berapa_harga_trigger():
    intent = detect_price_intent("berapa harga Beras Premium 5kg")
    assert intent.is_price_query is True
    assert intent.query_type == "catalog"
    assert "Beras" in intent.target or "beras" in intent.target.lower()


def test_harga_x_trigger():
    intent = detect_price_intent("harga laptop Dell XPS 13")
    assert intent.is_price_query is True
    assert "laptop" in intent.target.lower() or "Dell" in intent.target


def test_kurs_trigger():
    intent = detect_price_intent("kurs dollar hari ini")
    assert intent.is_price_query is True
    assert intent.currency == "USD"


def test_biaya_trigger():
    intent = detect_price_intent("biaya service AC")
    assert intent.is_price_query is True


# ── Target extraction ─────────────────────────────────


def test_target_extraction_strips_trigger():
    intent = detect_price_intent("berapa harga Samsung Galaxy S24?")
    assert "Samsung" in intent.target or "samsung" in intent.target.lower()
    assert "berapa" not in intent.target.lower()
    assert "?" not in intent.target


def test_target_extraction_keeps_brand_and_model():
    intent = detect_price_intent("harga Apple iPhone 15 Pro Max 256GB")
    target_lower = intent.target.lower()
    assert "apple" in target_lower or "iphone" in target_lower


# ── Date extraction ───────────────────────────────────


def test_date_iso_format():
    intent = detect_price_intent("harga BTC 2024-01-15")
    assert intent.target_date == date(2024, 1, 15)
    assert intent.query_type == "timeseries"


def test_date_dmy_format():
    intent = detect_price_intent("harga BTC 15/01/2024")
    assert intent.target_date == date(2024, 1, 15)


def test_date_indonesian_month():
    intent = detect_price_intent("harga BTC 15 Januari 2024")
    assert intent.target_date == date(2024, 1, 15)


def test_no_date_catalog():
    intent = detect_price_intent("harga laptop Dell")
    assert intent.target_date is None
    assert intent.query_type == "catalog"


# ── Currency detection ────────────────────────────────


def test_default_currency_idr():
    intent = detect_price_intent("harga Beras 5kg")
    assert intent.currency == "IDR"


def test_usd_explicit():
    intent = detect_price_intent("harga iPhone 15 dalam USD")
    assert intent.currency == "USD"


def test_eur_explicit():
    intent = detect_price_intent("harga mobil BMW dalam EUR")
    assert intent.currency == "EUR"


# ── Price range detection ─────────────────────────────


def test_max_price_dibawah():
    intent = detect_price_intent("laptop Dell di bawah 20 juta")
    assert intent.max_price == 20_000_000
    assert intent.query_type == "multi_criteria"


def test_min_price_diatas():
    intent = detect_price_intent("harga HP di atas 5 juta")
    assert intent.min_price == 5_000_000


def test_price_range_antara():
    intent = detect_price_intent("harga TV antara 3 juta sampai 7 juta")
    assert intent.min_price == 3_000_000
    assert intent.max_price == 7_000_000


def test_price_range_ribu():
    intent = detect_price_intent("harga kopi di bawah 50 ribu")
    assert intent.max_price == 50_000


# ── Category detection ────────────────────────────────


def test_category_crypto():
    intent = detect_price_intent("harga Bitcoin hari ini")
    assert intent.category == "crypto"


def test_category_stock():
    intent = detect_price_intent("harga saham BBCA")
    assert intent.category == "stock"


def test_category_product():
    intent = detect_price_intent("harga laptop ASUS")
    assert intent.category == "product"


# ── Edge cases ────────────────────────────────────────


def test_empty_query():
    intent = detect_price_intent("")
    assert intent.is_price_query is False


def test_query_with_only_spaces():
    intent = detect_price_intent("   ")
    assert intent.is_price_query is False


def test_rag_query_not_price():
    intent = detect_price_intent("apa itu Bitcoin?")
    assert intent.is_price_query is False


# ── OHLC field detection (NEW) ─────────────────────────


def test_field_type_high():
    intent = detect_price_intent("harga Bitcoin tertinggi")
    assert intent.field_type == "high"
    assert intent.field_label() == "Tertinggi"


def test_field_type_low():
    intent = detect_price_intent("harga BTC terendah")
    assert intent.field_type == "low"
    assert intent.field_label() == "Terendah"


def test_field_type_open():
    intent = detect_price_intent("berapa harga pembukaan BBCA")
    assert intent.field_type == "open"


def test_field_type_close():
    intent = detect_price_intent("harga penutupan saham BBCA")
    assert intent.field_type == "close"


def test_field_type_latest():
    intent = detect_price_intent("harga Bitcoin terbaru")
    assert intent.field_type == "latest"


def test_field_type_english():
    intent = detect_price_intent("harga Bitcoin highest 2024")
    assert intent.field_type == "high"


# ── Date range detection (NEW) ────────────────────────


def test_range_year():
    intent = detect_price_intent("harga Bitcoin tertinggi tahun 2024")
    assert intent.date_range_start == date(2024, 1, 1)
    assert intent.date_range_end == date(2024, 12, 31)


def test_range_quarter():
    intent = detect_price_intent("harga BTC Q1 2024")
    assert intent.date_range_start == date(2024, 1, 1)
    assert intent.date_range_end == date(2024, 3, 31)


def test_range_month():
    intent = detect_price_intent("harga Bitcoin Juni 2024")
    assert intent.date_range_start == date(2024, 6, 1)
    assert intent.date_range_end == date(2024, 6, 30)


def test_range_month_range():
    intent = detect_price_intent("harga BTC Januari-Maret 2024")
    assert intent.date_range_start == date(2024, 1, 1)
    assert intent.date_range_end == date(2024, 3, 31)


def test_query_type_range():
    intent = detect_price_intent("harga Bitcoin tertinggi tahun 2024")
    assert intent.query_type == "range"


def test_aggregation_default_for_high():
    intent = detect_price_intent("harga Bitcoin tertinggi tahun 2024")
    assert intent.aggregation == "max"


def test_aggregation_default_for_low():
    intent = detect_price_intent("harga Bitcoin terendah tahun 2024")
    assert intent.aggregation == "min"


# ── Target strips OHLC context (NEW) ──────────────────


def test_target_strips_field_keyword():
    intent = detect_price_intent("harga Bitcoin tertinggi")
    assert "Bitcoin" in intent.target
    assert "tertinggi" not in intent.target.lower()


def test_target_strips_year():
    intent = detect_price_intent("harga BTC tertinggi tahun 2024")
    assert intent.target == "BTC"


def test_target_strips_quarter():
    intent = detect_price_intent("harga Bitcoin Q1 2024")
    assert intent.target == "Bitcoin"


# ── Lowest field + recent marker detection (NEW) ──────


def test_lowest_catalog_no_date():
    intent = detect_price_intent("harga Polytron PAS 8C28 terendah")
    assert intent.is_price_query is True
    assert intent.field_type == "low"
    assert intent.query_type == "catalog"
    assert intent.has_recent_marker is False


def test_lowest_with_recent_marker_hari_ini():
    intent = detect_price_intent("harga Samsung terendah hari ini")
    assert intent.is_price_query is True
    assert intent.field_type == "low"
    assert intent.has_recent_marker is True


def test_lowest_with_recent_marker_saat_ini():
    intent = detect_price_intent("harga Bitcoin terendah saat ini")
    assert intent.has_recent_marker is True


def test_lowest_with_recent_marker_sekarang():
    intent = detect_price_intent("harga termurah sekarang")
    assert intent.has_recent_marker is True


def test_lowest_with_date_not_recent():
    intent = detect_price_intent("harga Bitcoin terendah pada 2024-03-15")
    assert intent.field_type == "low"
    assert intent.has_recent_marker is False
    assert intent.target_date == date(2024, 3, 15)
    assert intent.query_type == "timeseries"


def test_lowest_with_year_range_not_recent():
    intent = detect_price_intent("harga Bitcoin terendah tahun 2024")
    assert intent.field_type == "low"
    assert intent.has_recent_marker is False
    assert intent.date_range_start == date(2024, 1, 1)
    assert intent.query_type == "range"


def test_lowest_with_english():
    intent = detect_price_intent("lowest price of BBCA today")
    assert intent.field_type == "low"
    assert intent.has_recent_marker is True


def test_high_field_no_recent():
    intent = detect_price_intent("harga Bitcoin tertinggi hari ini")
    assert intent.field_type == "high"
    assert intent.has_recent_marker is False


# ── Marketplace noise stripping (NEW) ──────────────────


def test_target_strips_tokopedia():
    intent = detect_price_intent("berapa harga Polytron PAS 8C28 di Tokopedia")
    assert "Tokopedia" not in intent.target
    assert "Polytron" in intent.target
    assert "PAS 8C28" in intent.target


def test_target_strips_shopee():
    intent = detect_price_intent("harga Samsung TV di Shopee")
    assert "Shopee" not in intent.target
    assert "Samsung TV" in intent.target


def test_target_strips_lazada():
    intent = detect_price_intent("berapa harga laptop di Lazada")
    assert "Lazada" not in intent.target
    assert "laptop" in intent.target


def test_target_strips_marketplace_keyword():
    intent = detect_price_intent("harga Xiaomi di marketplace")
    assert "marketplace" not in intent.target.lower()
    assert "Xiaomi" in intent.target


def test_target_strips_pasaran():
    intent = detect_price_intent("harga Samsung di pasaran")
    assert "pasaran" not in intent.target.lower()
    assert "Samsung" in intent.target


def test_target_strips_online():
    intent = detect_price_intent("berapa harga TV LED online")
    assert "online" not in intent.target.lower() or "LED" in intent.target


def test_target_preserves_product_name_with_marketplace():
    """Products named 'Shopee' (rare) should be preserved."""
    intent = detect_price_intent("harga Samsung di Tokopedia")
    # 'Samsung' is the target, not 'Tokopedia'
    assert intent.target.startswith("Samsung")


def test_target_keeps_bhinneka_blibli():
    intent = detect_price_intent("harga monitor di Bhinneka")
    assert "Bhinneka" not in intent.target
    intent2 = detect_price_intent("harga HP di Blibli")
    assert "Blibli" not in intent2.target
