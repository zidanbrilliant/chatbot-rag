"""Auth middleware — JWT bearer token + role-based access.

Ponytail: dependency factory (require_role) over decorator pattern —
keeps FastAPI's OpenAPI schema correct.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_token

logger = logging.getLogger("chatbot")


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed token")
    token = authorization[7:]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return user


def require_role(*allowed_roles: str) -> Callable:
    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                403,
                f"Role '{user.role}' not authorized. Required: {list(allowed_roles)}",
            )
        return user
    return _checker
