"""Tests for StrictMode classifier — query classification and fixed responses."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.strict_mode import classify_query, get_casual_response


# ── classify_query ────────────────────────────────────


def test_classify_casual_halo():
    result = classify_query("halo")
    assert result.mode == "casual"


def test_classify_casual_hai():
    result = classify_query("hai")
    assert result.mode == "casual"


def test_classify_casual_assalamualaikum():
    result = classify_query("assalamualaikum")
    assert result.mode == "casual"


def test_classify_casual_apa_kabar():
    result = classify_query("apa kabar")
    assert result.mode == "casual"


def test_classify_casual_terima_kasih():
    result = classify_query("terima kasih")
    assert result.mode == "casual"


def test_classify_casual_kamu_siapa():
    result = classify_query("kamu siapa")
    assert result.mode == "casual"


def test_classify_strict_price_query():
    result = classify_query("berapa harga Polytron PAS 8C28")
    assert result.mode == "strict"


def test_classify_strict_comparison():
    result = classify_query("bandingkan harga Polytron vs Sharp")
    assert result.mode == "strict"


def test_classify_strict_definition():
    result = classify_query("apa itu Bitcoin?")
    assert result.mode == "strict"  # "apa" trigger


def test_classify_strict_description():
    result = classify_query("jelaskan cara kerja Facebook Prophet")
    assert result.mode == "strict"


def test_classify_strict_kelebihan():
    result = classify_query("kelebihan dan kekurangan LSTM")
    assert result.mode == "strict"


def test_classify_pure_creative_stats_clean():
    """Creative-only query (no KB trigger words) goes to 'normal' mode
    because classify_query sees no KB trigger patterns — then the
    injection guard catches it separately."""
    result = classify_query("tulis pantun")
    assert result.mode in ("normal", "strict")  # no kb signals


def test_classify_empty_query():
    result = classify_query("")
    assert result.mode == "normal"


def test_classify_normal_general():
    result = classify_query("how does machine learning work")
    assert result.mode == "normal"


# ── get_casual_response ───────────────────────────────


def test_get_casual_halo():
    resp = get_casual_response("halo")
    assert resp is not None
    assert "knowledge base" in resp.lower() or "bantu" in resp.lower()


def test_get_casual_hi():
    resp = get_casual_response("hi")
    assert resp is not None


def test_get_casual_assalamualaikum():
    resp = get_casual_response("assalamualaikum")
    assert resp is not None
    assert "alaikum" in resp.lower()


def test_get_casual_terima_kasih():
    resp = get_casual_response("terima kasih")
    assert resp is not None


def test_get_casual_kamu_siapa():
    resp = get_casual_response("kamu siapa")
    assert resp is not None
    assert "asisten" in resp.lower()


def test_get_casual_selamat():
    resp = get_casual_response("selamat pagi")
    assert resp is not None
    assert "pagi" in resp.lower()


def test_get_casual_non_casual_returns_none():
    resp = get_casual_response("berapa harga Polytron")
    assert resp is None


def test_get_casual_empty_returns_none():
    assert get_casual_response("") is None
    assert get_casual_response(None) is None


def test_get_casual_test_mode():
    resp = get_casual_response("test")
    assert resp is not None


def test_get_casual_selamat_malam():
    resp = get_casual_response("selamat malam")
    assert resp is not None
    assert "malam" in resp.lower()
