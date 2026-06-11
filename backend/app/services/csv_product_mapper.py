"""Parse product catalog CSV into structured products.

Supports schema: Barang;Brand;Tipe;Harga; Diskon (semicolon-separated,
EU/Indonesian price format like "Rp2.500.000,00").

Each row becomes a CSVProduct with name, sku, price, discount, category.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

logger = logging.getLogger("chatbot")


# Column name candidates (case-insensitive, whitespace-tolerant)
NAME_COLS = {"barang", "nama", "product", "produk", "item", "nama_produk", "name"}
BRAND_COLS = {"brand", "merek", "merk", "manufacturer"}
TIPE_COLS = {"tipe", "type", "model", "seri", "series"}
PRICE_COLS = {"harga", "price", "biaya", "tarif", "cost", "amount", "nilai"}
DISCOUNT_COLS = {"diskon", "discount", "potongan", "promo", "promotion", "harga_diskon"}


@dataclass
class CSVProduct:
    """One product parsed from CSV row."""

    name: str
    sku: str
    category: str
    brand: str
    tipe: str
    price: Decimal
    discount_price: Decimal | None
    raw_row: dict


def parse_product_csv(file_path: str) -> list[CSVProduct]:
    """Parse product catalog CSV into structured products.

    Auto-detects separator and encoding.
    """
    # Read with auto-detection
    df = _read_csv_flexible(file_path)
    if df is None:
        raise ValueError(f"Could not read CSV: {file_path}")

    # Find columns
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    name_col = _find_first(cols_lower, NAME_COLS)
    brand_col = _find_first(cols_lower, BRAND_COLS)
    tipe_col = _find_first(cols_lower, TIPE_COLS)
    price_col = _find_first(cols_lower, PRICE_COLS)
    discount_col = _find_first(cols_lower, DISCOUNT_COLS)

    if not name_col or not price_col:
        raise ValueError(
            f"Required columns not found. Have: {list(df.columns)}. "
            f"Need at minimum: name column and price column."
        )

    products: list[CSVProduct] = []
    for _, row in df.iterrows():
        try:
            name_raw = str(row[name_col]).strip() if name_col else ""
            if not name_raw:
                continue

            brand = str(row[brand_col]).strip() if brand_col else ""
            tipe = str(row[tipe_col]).strip() if tipe_col else ""
            price_raw = str(row[price_col]).strip()
            price = _parse_price(price_raw)
            if price is None or price <= 0:
                continue

            discount = None
            if discount_col:
                discount_raw = str(row[discount_col]).strip()
                discount = _parse_price(discount_raw) if discount_raw else None

            full_name = " ".join(filter(None, [name_raw, brand, tipe]))
            full_name = _normalize_name(full_name)
            sku = _generate_sku(brand, tipe, name_raw)
            category = _detect_category(name_raw)

            products.append(CSVProduct(
                name=full_name,
                sku=sku,
                category=category,
                brand=brand,
                tipe=tipe,
                price=price,
                discount_price=discount,
                raw_row={k: str(v) for k, v in row.items()},
            ))
        except Exception as e:
            logger.debug("Skip row: %s", e)
            continue

    return products


def _read_csv_flexible(file_path: str) -> pd.DataFrame | None:
    """Read CSV with auto-detect separator and encoding."""
    # First try pd.read_csv with sep=None (sniff) — works for well-formed files
    for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        for sep in (None, ";", ",", "\t", "|"):
            try:
                if sep is None:
                    # engine="python" doesn't support low_memory=False
                    df = pd.read_csv(
                        file_path, sep=None, engine="python",
                        encoding=encoding,
                    )
                else:
                    df = pd.read_csv(
                        file_path, sep=sep, encoding=encoding, low_memory=False,
                    )
                # Sanity check: must have at least 1 column
                if df.shape[1] < 1:
                    continue
                # If sep=None produced 1 column, the sniffer failed — try explicit seps
                if df.shape[1] == 1 and sep is None:
                    continue
                # Strip whitespace from column names
                df.columns = [str(c).strip() for c in df.columns]
                return df
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                continue

    # Fallback: detect separator by counting characters in first line
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
        candidates = {";": first_line.count(";"), ",": first_line.count(","),
                      "\t": first_line.count("\t"), "|": first_line.count("|")}
        best = max(candidates.items(), key=lambda x: x[1])
        if best[1] > 0:
            for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
                try:
                    df = pd.read_csv(
                        file_path, sep=best[0], encoding=encoding, low_memory=False,
                    )
                    df.columns = [str(c).strip() for c in df.columns]
                    if df.shape[1] > 1:
                        return df
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _find_first(cols_lower: dict, candidates: set[str]) -> str | None:
    """Find the first column matching any candidate name."""
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _parse_price(s: str) -> Decimal | None:
    """Parse 'Rp2.500.000,00' or 'Rp 2.500.000' formats.

    Handles:
    - EU format: dots as thousands, comma as decimal (2.500.000,00)
    - US format: commas as thousands, dot as decimal (2,500,000.00)
    - IDR format: dots as thousands, no decimal (2.500.000)
    - Bare digits: 2500000
    - With/without Rp/IDR/USD prefix
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None

    # Remove currency markers
    s = re.sub(r"(rp|rupiah|idr|usd|\$|€|eur)", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return None

    # EU format: "2.500.000,00" (dots thousands, comma decimal)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Ambiguous: could be thousands "1,500" or decimal "1,5"
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    else:
        # Only dots: could be IDR thousands "2.500.000" or decimal "1.5"
        parts = s.split(".")
        if (
            len(parts) >= 2
            and all(len(p) == 3 for p in parts[1:])
            and parts[0].isdigit()
        ):
            s = s.replace(".", "")

    if not re.match(r"^-?\d+(\.\d+)?$", s):
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _generate_sku(brand: str, tipe: str, name: str) -> str:
    parts: list[str] = []
    if brand:
        parts.append(re.sub(r"[^A-Z0-9]", "", brand.upper())[:8])
    if tipe:
        parts.append(re.sub(r"[^A-Z0-9]", "", tipe.upper())[:12])
    if not parts:
        parts.append(re.sub(r"[^A-Z0-9]", "", name.upper())[:12])
    sku = "-".join(parts)
    return sku or "UNKNOWN"


def _detect_category(name: str) -> str:
    """Detect product category from name keywords."""
    n = name.upper()
    if any(k in n for k in ("SPEAKER", "SPEAKAR", "SPEAPER", "SPEAKR")):
        return "speaker"
    if any(k in n for k in ("LED",)):
        return "led_tv"
    if "TV" in n:
        return "tv"
    if "MESIN" in n:
        return "appliance"
    if "AC" in n and "SPEAKER" not in n:
        return "ac"
    if "KULKAS" in n or "LEMARI ES" in n:
        return "refrigerator"
    if "MESIN CUCI" in n:
        return "washing_machine"
    return "other"


# Common typos in product catalogs (especially barang.csv from Polytron)
TYPO_FIXES = [
    (re.compile(r"\bSPEAKAR\b", re.IGNORECASE), "SPEAKER"),
    (re.compile(r"\bSPEAPER\b", re.IGNORECASE), "SPEAKER"),
    (re.compile(r"\bSPEAKR\b", re.IGNORECASE), "SPEAKER"),
]


def _normalize_name(name: str) -> str:
    """Apply common typo fixes to product name for better searchability."""
    out = name
    for pattern, replacement in TYPO_FIXES:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s+", " ", out).strip()
