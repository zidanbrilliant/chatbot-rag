"""Tests for StrictMode — fixed casual responses."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.strict_mode import get_casual_response

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
