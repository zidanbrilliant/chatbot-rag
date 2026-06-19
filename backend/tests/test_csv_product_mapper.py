import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.csv_product_mapper import (
    _detect_category,
    _generate_sku,
    _parse_price,
    parse_product_csv,
)

# ── _parse_price helper ────────────────────────────────


def test_parse_price_idr_eu_format():
    """Rp2.500.000,00 format (EU thousands sep + comma decimal)."""
    assert _parse_price("Rp2.500.000,00") == Decimal("2500000.00")


def test_parse_price_idr_space_format():
    """Rp 2.500.000 format with space."""
    assert _parse_price("Rp 2.500.000") == Decimal("2500000")


def test_parse_price_us_format():
    """US format: commas thousands, dot decimal."""
    assert _parse_price("$1,500.00") == Decimal("1500.00")


def test_parse_price_bare_digits():
    assert _parse_price("50000") == Decimal("50000")


def test_parse_price_with_currency_prefix():
    assert _parse_price("IDR 1.500.000") == Decimal("1500000")


def test_parse_price_decimal_comma_only():
    """Ambiguous: 1,5 could be 1500 or 1.5."""
    # We treat 3 digits after comma as thousands
    assert _parse_price("1,500") == Decimal("1500")
    # 2 digits treated as decimal
    assert _parse_price("1,50") == Decimal("1.50")


def test_parse_price_invalid():
    assert _parse_price("") is None
    assert _parse_price(None) is None
    assert _parse_price("abc") is None
    assert _parse_price("Rp abc") is None


def test_parse_price_negative():
    # Negative numbers not really expected in prices
    result = _parse_price("-100")
    # Should return -100 as Decimal (won't be filtered out by price check)
    assert result == Decimal("-100")


# ── _detect_category helper ────────────────────────────


def test_detect_category_speaker():
    assert _detect_category("SPEAKER AKTIF") == "speaker"
    assert _detect_category("SPEAKAR AKTIF") == "speaker"  # typo
    assert _detect_category("SPEAPER AKTIF") == "speaker"  # typo


def test_detect_category_led():
    assert _detect_category("LED TV") == "led_tv"
    assert _detect_category("LED (SEMI TABUNG)") == "led_tv"


def test_detect_category_tv():
    assert _detect_category("SMART TV") == "tv"


def test_detect_category_other():
    assert _detect_category("RANDOM PRODUCT") == "other"


# ── _generate_sku helper ───────────────────────────────


def test_generate_sku_brand_tipe():
    sku = _generate_sku("POLYTRON", "PAS 8C28", "")
    assert "POLYTRON" in sku
    assert "PAS8C28" in sku


def test_generate_sku_no_tipe():
    sku = _generate_sku("POLYTRON", "", "SPEAKER AKTIF")
    assert "POLYTRON" in sku


def test_generate_sku_no_brand():
    sku = _generate_sku("", "PAS 8C28", "SPEAKER AKTIF")
    assert "PAS8C28" in sku


# ── parse_product_csv (full file parse) ──────────────


def test_parse_csv_with_semicolon():
    """barang.csv uses ; separator — must auto-detect."""
    csv_content = (
        "Barang;Brand;Tipe;Harga; Diskon \n"
        "SPEAKER AKTIF;POLYTRON;PAS 8C28;Rp2.500.000,00;Rp2.335.000,00\n"
        "LED;POLYTRON;32BV1558;Rp2.300.000,00;Rp2.150.000,00\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(csv_content)
        path = f.name
    try:
        products = parse_product_csv(path)
        assert len(products) == 2
        p1 = products[0]
        assert "SPEAKER AKTIF" in p1.name
        assert p1.brand == "POLYTRON"
        assert p1.tipe == "PAS 8C28"
        assert p1.price == Decimal("2500000.00")
        assert p1.discount_price == Decimal("2335000.00")
        assert p1.category == "speaker"
    finally:
        os.unlink(path)


def test_parse_csv_whitespace_in_column_names():
    """Column ' Diskon ' has leading/trailing space — must be stripped."""
    csv_content = "Barang;Brand;Tipe;Harga; Diskon \nSPEAKER;X;Y;100;80\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(csv_content)
        path = f.name
    try:
        products = parse_product_csv(path)
        assert len(products) == 1
        assert products[0].price == Decimal("100")
        assert products[0].discount_price == Decimal("80")
    finally:
        os.unlink(path)


def test_parse_csv_with_comma_separator():
    """Standard CSV with comma should also work."""
    csv_content = (
        "name,brand,price\n"
        "Apple iPhone,Apple,15000000\n"
        "Samsung Galaxy,Samsung,12000000\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(csv_content)
        path = f.name
    try:
        products = parse_product_csv(path)
        assert len(products) == 2
        assert "iPhone" in products[0].name
        assert products[0].price == Decimal("15000000")
    finally:
        os.unlink(path)


def test_parse_csv_real_barang():
    """Test against the real barang.csv file if it exists."""
    real_path = Path(__file__).parent.parent.parent.parent / "data" / "barang.csv"
    if not real_path.exists():
        return  # skip if not available

    products = parse_product_csv(str(real_path))
    assert len(products) > 100, f"Expected 100+ products, got {len(products)}"

    # Spot-check first product
    p = products[0]
    assert p.brand == "POLYTRON" or p.brand == "POLYTRON "
    assert p.price > 0
    assert p.sku
    assert p.category in ("speaker", "led_tv", "tv", "other")


# ── SKU uniqueness (row-index suffix) ──────────────────


def test_sku_unique_across_duplicate_rows():
    """Same brand+tipe on multiple CSV rows must produce distinct SKUs."""
    from app.services.csv_product_mapper import _generate_sku

    sku1 = _generate_sku("POLYTRON", "PAS 8B28", "SPEAKER AKTIF", row_idx=4)
    sku2 = _generate_sku("POLYTRON", "PAS 8B28", "SPEAKER AKTIF", row_idx=6)
    assert sku1 != sku2
    assert "R004" in sku1
    assert "R006" in sku2


def test_sku_no_row_idx_keeps_legacy_format():
    """Without row_idx, SKU is brand-tipe (legacy behavior preserved)."""
    from app.services.csv_product_mapper import _generate_sku

    sku = _generate_sku("SHARP", "24 DC1I", "LED")
    assert "R0" not in sku  # No R0xx row suffix
    assert sku == "SHARP-24DC1I"


# ── Typo fixes (AIR COOLEER, FREEEZER) ─────────────────


def test_typo_fix_air_cooleer():
    from app.services.csv_product_mapper import _normalize_name

    assert _normalize_name("AIR COOLEER MIDEA") == "AIR COOLER MIDEA"


def test_typo_fix_freeezer():
    from app.services.csv_product_mapper import _normalize_name

    assert _normalize_name("FREEEZER BOX SHARP") == "FREEZER BOX SHARP"


def test_typo_fix_preserves_speaker_typos():
    """Existing SPEAKAR/SPEAPER fixes still work."""
    from app.services.csv_product_mapper import _normalize_name

    assert _normalize_name("SPEAKAR AKTIF") == "SPEAKER AKTIF"
    assert _normalize_name("SPEAPER AKTIF") == "SPEAKER AKTIF"


# ── Real barang.csv: no duplicate SKUs anymore ──────────


def test_barang_csv_no_duplicate_skus():
    """All SKU values in barang.csv must be unique (after row-index fix)."""
    real_path = Path(__file__).parent.parent.parent.parent / "data" / "barang.csv"
    if not real_path.exists():
        return

    products = parse_product_csv(str(real_path))
    skus = [p.sku for p in products]
    assert len(skus) == len(set(skus)), (
        f"Found duplicate SKUs in barang.csv: "
        f"{[s for s in skus if skus.count(s) > 1]}"
    )
