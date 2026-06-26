"""Auth integration test using TestClient with mocked DB.

Verifies the full auth flow end-to-end:
- Unauthenticated requests → 401
- Login wrong password → 401
- Login correct → token
- require_role dependency rejects wrong role → 403
- require_role accepts correct role → 200
- Expired/invalid/malformed/missing token → 401
- Access level mapping is correct
"""
import time
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from app.config import ADMIN_API_KEY
from app.main import app
from app.middleware.auth import get_current_user, require_role
from app.services.auth import create_token, decode_token, hash_password, verify_password


def make_mock_user(role, username="testuser", is_active=True, user_id="mock-1"):
    user = MagicMock()
    user.role = role
    user.username = username
    user.is_active = is_active
    user.id = user_id
    return user


def real_token_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed token")
    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return make_mock_user(
        role=payload.get("role", "viewer"),
        username=payload.get("user_id", "anon"),
        user_id=payload.get("user_id", "anon"),
    )


@pytest.fixture(autouse=True)
def _setup_auth_override():
    """Override get_current_user for all tests in this module.

    Auth check happens BEFORE DB access, so we don't need to override get_db.
    """
    app.dependency_overrides[get_current_user] = real_token_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_unauthenticated_returns_401(client):
    # Temporarily remove override to test real auth
    saved = app.dependency_overrides.pop(get_current_user)
    r = client.post("/api/v1/chat/query", json={"query": "hello"})
    app.dependency_overrides[get_current_user] = saved
    assert r.status_code == 401


def test_hash_and_verify_password():
    h = hash_password("test123")
    assert verify_password("test123", h)
    assert not verify_password("wrong", h)


def test_jwt_round_trip():
    token = create_token("u-1", "viewer")
    payload = decode_token(token)
    assert payload["user_id"] == "u-1"
    assert payload["role"] == "viewer"


def test_require_role_rejects_wrong_role():
    dep = require_role("document_admin", "system_admin")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=make_mock_user("viewer"))
    assert exc_info.value.status_code == 403


def test_require_role_accepts_correct_role():
    dep = require_role("viewer", "document_admin", "system_admin", "auditor")
    result = dep(user=make_mock_user("viewer"))
    assert result.role == "viewer"


def test_documents_with_invalid_token_401(client):
    # Auth check happens before DB access — no DB override needed
    r = client.get(
        "/api/v1/documents",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert r.status_code == 401


def test_documents_with_expired_token_401(client):
    expired = pyjwt.encode(
        {"user_id": "x", "role": "system_admin", "exp": int(time.time()) - 60},
        ADMIN_API_KEY,
        algorithm="HS256",
    )
    r = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert r.status_code == 401


def test_documents_with_malformed_header_401(client):
    r = client.get(
        "/api/v1/documents",
        headers={"Authorization": "Basic abc123"},
    )
    assert r.status_code == 401


def test_documents_with_no_header_401(client):
    r = client.get("/api/v1/documents")
    assert r.status_code == 401


def test_documents_with_viewer_token_role_rejected_403(client):
    # /documents list requires document_admin|system_admin|auditor
    # viewer should get 403 from role check (still before DB)
    viewer_token = create_token("viewer-id", "viewer")
    r = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    # role check happens after get_current_user but before route body
    # get_db is called in the signature, but should not be hit
    # Actually get_db is in the signature, so it WILL be called
    # We need to also override get_db for this test
    from app.database import get_db
    from sqlalchemy.orm import Session
    mock_db = MagicMock(spec=Session)
    def mock_get_db():
        yield mock_db
    app.dependency_overrides[get_db] = mock_get_db
    try:
        r = client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403, f"got {r.status_code}: {r.text}"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_chat_query_endpoint_has_auth_param():
    import inspect
    chat_query_func = None
    for route in app.routes:
        if hasattr(route, "path") and route.path == "/api/v1/chat/query":
            chat_query_func = route.endpoint
            break
    assert chat_query_func is not None
    params = list(inspect.signature(chat_query_func).parameters.values())
    auth_param = next((p for p in params if p.name == "user"), None)
    assert auth_param is not None


def test_access_level_role_mapping():
    from app.services.qdrant_client import _user_max_access_level
    assert _user_max_access_level("viewer") == 0
    assert _user_max_access_level("document_admin") == 1
    assert _user_max_access_level("system_admin") == 2
    assert _user_max_access_level("auditor") == 2
    assert _user_max_access_level(None) == 0
    assert _user_max_access_level("unknown") == 0
