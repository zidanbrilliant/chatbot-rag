import logging
import os
import re
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR

logger = logging.getLogger("chatbot")

_DATE_PATTERNS = [
    re.compile(
        r"(\d{1,2})\s+(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})"),
    re.compile(r"tanggal\s+(\d{1,2})"),
]

_MONTH_MAP = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}

_COLUMN_KEYWORDS = {
    "terendah": "Low",
    "tertinggi": "High",
    "rendah": "Low",
    "tinggi": "High",
    "low": "Low",
    "high": "High",
    "pembukaan": "Open",
    "buka": "Open",
    "open": "Open",
    "penutupan": "Close",
    "tutup": "Close",
    "close": "Close",
    "volume": "Volume",
    "harga": None,
}


def _parse_date(text: str) -> str | None:
    text_lower = text.lower()

    for pat in _DATE_PATTERNS:
        m = pat.search(text_lower)
        if not m:
            continue
        groups = m.groups()

        if len(groups) == 3:
            if pat == _DATE_PATTERNS[0]:
                day, month_name, year = int(groups[0]), groups[1].lower(), int(groups[2])
                month = _MONTH_MAP.get(month_name)
                if month:
                    return f"{year:04d}-{month:02d}-{day:02d}"
                return f"{year:04d}"
            elif pat == _DATE_PATTERNS[1]:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                return f"{year:04d}-{month:02d}-{day:02d}"
            elif pat == _DATE_PATTERNS[2]:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                return f"{year:04d}-{month:02d}-{day:02d}"

    m = re.search(r"(\d{4})", text)
    if m:
        return m.group(1)
    return None


def _find_tabular_files() -> list[str]:
    files = []
    if not os.path.isdir(DATA_DIR):
        return files
    for entry in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, entry)
        if not os.path.isfile(path):
            continue
        ext = Path(entry).suffix.lower()
        if ext in (".csv", ".xlsx"):
            file_size = os.path.getsize(path)
            if 100 < file_size < 50 * 1024 * 1024:
                files.append(path)
    return files


def extract_tabular_fact(
    query: str, file_path_hint: str | None = None
) -> tuple[str | None, str | None]:
    query_lower = query.lower()

    date_str = _parse_date(query)
    if not date_str:
        return None, None

    target_column = "Low"
    for keyword, column in _COLUMN_KEYWORDS.items():
        if keyword in query_lower:
            if column is not None:
                target_column = column
            break

    candidates = []
    if file_path_hint and os.path.isfile(file_path_hint):
        candidates.append(file_path_hint)
    
    for f in _find_tabular_files():
        if f not in candidates:
            candidates.append(f)

    if not candidates:
        return None, None

    for file_path in candidates:
        try:
            ext = Path(file_path).suffix.lower()
            if ext == ".csv":
                df = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
            elif ext == ".xlsx":
                df = pd.read_excel(file_path, sheet_name=0)
            else:
                continue

            df = df.fillna("")
            date_col = None
            for col in df.columns:
                col_lower = str(col).strip().lower()
                if col_lower in ("date", "tanggal", "datetime", "time", "timestamp", "date & time"):
                    date_col = col
                    break

            if date_col is None:
                continue

            df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
            target_date = str(date_str)

            match = df[df[date_col] == target_date]
            if match.empty:
                match = df[df[date_col].str.contains(target_date, na=False)]
            
            if match.empty:
                for part_len in (10, 7):
                    part = target_date[:part_len]
                    match = df[df[date_col].str.startswith(part, na=False)]
                    if not match.empty:
                        break

            if match.empty:
                continue

            row = match.iloc[0]
            cols_map = {str(c).strip().lower(): str(c) for c in df.columns}
            target_col_actual = None
            for name, actual in cols_map.items():
                if target_column.lower() == name or name.startswith(target_column.lower()):
                    target_col_actual = actual
                    break

            if target_col_actual:
                raw_val = row[target_col_actual]
                fact = f"[FAKTA TERVERIFIKASI DARI FILE: {Path(file_path).name}] Pada tanggal {target_date}, {target_column} Bitcoin adalah {raw_val}."
                logger.info("Structured fact extracted: %s", fact[:120])
                return fact, Path(file_path).name
            else:
                row_preview = " | ".join(f"{c}: {row[c]}" for c in df.columns[:6])
                fact = f"[FAKTA TERVERIFIKASI DARI FILE: {Path(file_path).name}] Data untuk tanggal {target_date}: {row_preview}"
                return fact, Path(file_path).name

        except Exception as e:
            logger.warning("Structured extraction failed for %s: %s", file_path, str(e)[:200])
            continue

    return None, None
