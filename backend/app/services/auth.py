"""Auth service — password hashing + JWT.

Ponytail: stdlib hashlib + secrets for hashing (skip bcrypt dep),
PyJWT for token encode/decode (already installed).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Any

import jwt

from app.config import ADMIN_API_KEY

logger = logging.getLogger("chatbot")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 86400


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split("$", 1)
    except ValueError:
        return False
    actual = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return secrets.compare_digest(actual, expected)


def create_token(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, ADMIN_API_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, ADMIN_API_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as e:
        logger.debug("JWT decode failed: %s", e)
        return None
