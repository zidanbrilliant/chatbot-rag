"""Tests for auth service (hash, verify, JWT)."""
import time

import pytest

from app.services.auth import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_password_format():
    h = hash_password("test123")
    assert "$" in h
    salt, digest = h.split("$", 1)
    assert len(salt) == 32
    assert len(digest) == 64


def test_hash_password_unique_salt():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b


def test_verify_password_correct():
    h = hash_password("my_password")
    assert verify_password("my_password", h) is True


def test_verify_password_wrong():
    h = hash_password("my_password")
    assert verify_password("wrong", h) is False


def test_verify_password_malformed_hash():
    assert verify_password("anything", "no-dollarsign") is False
    assert verify_password("anything", "only$one$part$extra") is False


def test_create_and_decode_token():
    token = create_token("user-123", "viewer")
    payload = decode_token(token)
    assert payload is not None
    assert payload["user_id"] == "user-123"
    assert payload["role"] == "viewer"


def test_decode_invalid_token():
    assert decode_token("not-a-real-jwt") is None


def test_decode_expired_token():
    from app.services.auth import JWT_ALGORITHM
    from app.config import ADMIN_API_KEY
    import jwt

    expired = jwt.encode(
        {"user_id": "u1", "role": "viewer", "exp": int(time.time()) - 60},
        ADMIN_API_KEY,
        algorithm=JWT_ALGORITHM,
    )
    assert decode_token(expired) is None
