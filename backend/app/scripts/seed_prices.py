"""Sample data seeder for products, single prices, and OHLC time-series.

Run from backend/:
    python -m app.scripts.seed_prices

Idempotent — skips products that already exist (by SKU).
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import SessionLocal
from app.models.price import PriceOHLC, Product, ProductPrice

logger = logging.getLogger("chatbot.seed")
logging.basicConfig(level=logging.INFO)


SAMPLE_PRODUCTS: list[dict] = [
    {
        "sku": "BR-PREM-5KG",
        "name": "Beras Premium 5kg",
        "category": "product",
        "unit": "5kg",
        "description": "Beras premium kualitas terbaik, 5 kilogram",
        "attributes": {"brand": "Pandan Wangi", "type": "beras"},
        "single_prices": [
            (Decimal("75000"), date(2024, 1, 15), "Toko Sumber Rezeki"),
            (Decimal("78000"), date(2024, 6, 1), "Toko Sumber Rezeki"),
            (Decimal("80000"), date(2025, 1, 10), "Toko Sumber Rezeki"),
        ],
        # OHLC not relevant for retail product
    },
    {
        "sku": "MYR-BML-1L",
        "name": "Minyak Goreng Bimoli 1L",
        "category": "product",
        "unit": "1L",
        "attributes": {"brand": "Bimoli"},
        "single_prices": [
            (Decimal("25000"), date(2024, 1, 15), "Indomaret"),
            (Decimal("28000"), date(2024, 6, 1), "Indomaret"),
        ],
    },
    {
        "sku": "BTC",
        "name": "Bitcoin",
        "category": "crypto",
        "unit": "BTC",
        "attributes": {"symbol": "BTC"},
        "single_prices": [
            # Latest single price for catalog queries
            (Decimal("1500000000"), date(2025, 1, 10), "Indodax"),
        ],
        # 12 months of OHLC for 2024 — supports "highest/lowest 2024" queries
        "ohlc": [
            (date(2024, 1, 1),  Decimal("420000000"),  Decimal("450000000"),  Decimal("380000000"),  Decimal("445000000"),  Decimal("12500")),
            (date(2024, 2, 1),  Decimal("445000000"),  Decimal("510000000"),  Decimal("430000000"),  Decimal("498000000"),  Decimal("15800")),
            (date(2024, 3, 1),  Decimal("498000000"),  Decimal("620000000"),  Decimal("490000000"),  Decimal("610000000"),  Decimal("22400")),
            (date(2024, 4, 1),  Decimal("610000000"),  Decimal("710000000"),  Decimal("580000000"),  Decimal("650000000"),  Decimal("18900")),
            (date(2024, 5, 1),  Decimal("650000000"),  Decimal("700000000"),  Decimal("620000000"),  Decimal("680000000"),  Decimal("16700")),
            (date(2024, 6, 1),  Decimal("680000000"),  Decimal("725000000"),  Decimal("640000000"),  Decimal("700000000"),  Decimal("14200")),
            (date(2024, 7, 1),  Decimal("700000000"),  Decimal("700000000"),  Decimal("550000000"),  Decimal("620000000"),  Decimal("21300")),
            (date(2024, 8, 1),  Decimal("620000000"),  Decimal("660000000"),  Decimal("580000000"),  Decimal("640000000"),  Decimal("17800")),
            (date(2024, 9, 1),  Decimal("640000000"),  Decimal("680000000"),  Decimal("600000000"),  Decimal("660000000"),  Decimal("16500")),
            (date(2024, 10, 1), Decimal("660000000"),  Decimal("720000000"),  Decimal("650000000"),  Decimal("700000000"),  Decimal("19200")),
            (date(2024, 11, 1), Decimal("700000000"),  Decimal("990000000"),  Decimal("680000000"),  Decimal("960000000"),  Decimal("28500")),
            (date(2024, 12, 1), Decimal("960000000"),  Decimal("1080000000"), Decimal("920000000"), Decimal("1010000000"), Decimal("24100")),
        ],
    },
    {
        "sku": "BBCA",
        "name": "Saham BBCA",
        "category": "stock",
        "unit": "lembar",
        "attributes": {"symbol": "BBCA", "exchange": "IDX"},
        "single_prices": [
            (Decimal("10250"), date(2024, 6, 1), "Stockbit"),
        ],
        # Quarterly OHLC for 2023-2024
        "ohlc": [
            (date(2024, 1, 1),  Decimal("9875"),  Decimal("10250"), Decimal("9650"),  Decimal("10100"), Decimal("125000000")),
            (date(2024, 4, 1),  Decimal("10100"), Decimal("10550"), Decimal("10050"), Decimal("10350"), Decimal("118000000")),
            (date(2024, 7, 1),  Decimal("10350"), Decimal("10700"), Decimal("10100"), Decimal("10450"), Decimal("98000000")),
            (date(2024, 10, 1), Decimal("10450"), Decimal("11050"), Decimal("10300"), Decimal("10800"), Decimal("115000000")),
            (date(2025, 1, 1),  Decimal("10800"), Decimal("11250"), Decimal("10650"), Decimal("11050"), Decimal("108000000")),
        ],
    },
    {
        "sku": "LPT-AS-ROG",
        "name": "Laptop ASUS ROG Strix G15",
        "category": "product",
        "unit": "unit",
        "description": "Laptop gaming ASUS ROG Strix G15, RTX 3060, RAM 16GB",
        "attributes": {"brand": "ASUS", "model": "ROG Strix G15", "ram_gb": 16},
        "single_prices": [
            (Decimal("18500000"), date(2024, 6, 1), "Tokopedia"),
            (Decimal("19900000"), date(2025, 1, 10), "Tokopedia"),
        ],
    },
    {
        "sku": "HP-SM-S24",
        "name": "Samsung Galaxy S24",
        "category": "product",
        "unit": "unit",
        "attributes": {"brand": "Samsung", "model": "Galaxy S24", "storage_gb": 256},
        "single_prices": [
            (Decimal("13999000"), date(2024, 1, 15), "Samsung Official Store"),
            (Decimal("12999000"), date(2025, 1, 10), "Samsung Official Store"),
        ],
    },
    {
        "sku": "GLS-PSR-1KG",
        "name": "Gula Pasir Premium 1kg",
        "category": "product",
        "unit": "1kg",
        "single_prices": [
            (Decimal("18000"), date(2024, 1, 15), "Alfamart"),
            (Decimal("20000"), date(2024, 6, 1), "Alfamart"),
        ],
    },
]


def seed() -> None:
    """Insert sample products, single prices, and OHLC rows. Idempotent on SKU."""
    db = SessionLocal()
    try:
        for p_data in SAMPLE_PRODUCTS:
            existing = (
                db.query(Product).filter(Product.sku == p_data["sku"]).first()
            )
            if existing:
                logger.info("Skip existing product: %s", p_data["sku"])
                continue

            product = Product(
                sku=p_data["sku"],
                name=p_data["name"],
                category=p_data.get("category"),
                unit=p_data.get("unit"),
                description=p_data.get("description"),
                attributes=p_data.get("attributes"),
                source="seed",
            )
            db.add(product)
            db.flush()

            for value, dt, supplier in p_data.get("single_prices", []):
                db.add(ProductPrice(
                    product_id=product.id,
                    price=value,
                    currency="IDR",
                    price_date=dt,
                    supplier=supplier,
                    source="seed",
                ))

            for ohlc_row in p_data.get("ohlc", []):
                trade_date, o, h, l, c, vol = ohlc_row
                db.add(PriceOHLC(
                    product_id=product.id,
                    trade_date=trade_date,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=vol,
                    currency="IDR",
                    source="seed",
                ))

            single_count = len(p_data.get("single_prices", []))
            ohlc_count = len(p_data.get("ohlc", []))
            logger.info(
                "Inserted: %s (%d single, %d OHLC)",
                p_data["name"], single_count, ohlc_count,
            )
        db.commit()
        logger.info("Seed complete.")
    except Exception as e:
        db.rollback()
        logger.error("Seed failed: %s", str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
