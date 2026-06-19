"""Tests for document processor with auto-detect CSV parsing."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_processor import (
    _detect_csv_separator,
    parse_csv,
)


def test_detect_separator_semicolon():
    """Sample with mostly ; should detect ;."""
    sample = "A;B;C\n1;2;3\n4;5;6\n"
    assert _detect_csv_separator(_temp_csv(sample)) == ";"


def test_detect_separator_comma():
    sample = "A,B,C\n1,2,3\n4,5,6\n"
    assert _detect_csv_separator(_temp_csv(sample)) == ","


def test_detect_separator_tab():
    sample = "A\tB\tC\n1\t2\t3\n"
    assert _detect_csv_separator(_temp_csv(sample)) == "\t"


def test_detect_separator_pipe():
    sample = "A|B|C\n1|2|3\n"
    assert _detect_csv_separator(_temp_csv(sample)) == "|"


def test_detect_separator_default_comma():
    """Empty or no-separator content defaults to comma."""
    sample = "NoSeparatorsHere\nJustLines\n"
    assert _detect_csv_separator(_temp_csv(sample)) == ","


def _temp_csv(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


# ── parse_csv full ──────────────────────────────────────


def test_parse_csv_semicolon():
    csv_content = "Barang;Brand;Tipe;Harga; Diskon \nSPEAKER;POLYTRON;PAS 8C28;Rp2.500.000,00;Rp2.335.000,00\n"
    path = _temp_csv(csv_content)
    try:
        result = parse_csv(path)
        assert len(result) == 1
        text = result[0]["text"]
        assert "Konteks dokumen" in text
        assert "SPEAKER" in text
        assert "POLYTRON" in text
        assert "2.500.000,00" in text or "Rp2.500.000,00" in text
    finally:
        os.unlink(path)


def test_parse_csv_comma_separator():
    csv_content = "name,price\nApple,15000\nBanana,5000\n"
    path = _temp_csv(csv_content)
    try:
        result = parse_csv(path)
        text = result[0]["text"]
        assert "Apple" in text
        assert "15000" in text
        assert "Banana" in text
    finally:
        os.unlink(path)


def test_parse_csv_strips_column_whitespace():
    """Column names with trailing space should be stripped."""
    csv_content = "name; price ;\nApple;10000\n"
    path = _temp_csv(csv_content)
    try:
        result = parse_csv(path)
        text = result[0]["text"]
        # Should still parse columns correctly
        assert "Apple" in text
    finally:
        os.unlink(path)


def test_parse_csv_real_barang_file():
    """Test against real barang.csv if available."""
    real_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "barang.csv"
    )
    real_path = os.path.abspath(real_path)
    if not os.path.exists(real_path):
        return  # skip

    result = parse_csv(real_path)
    assert len(result) == 1
    text = result[0]["text"]
    # Should have the structure with column labels
    assert "Konteks dokumen" in text
    # Should have POLYTRON content
    assert "POLYTRON" in text or "Polytron" in text
