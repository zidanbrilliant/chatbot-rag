"""Auth router — login + register endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import require_role
from app.models.user import ROLE_LEVEL, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import create_token, hash_password, verify_password

logger = logging.getLogger("chatbot")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    token = create_token(str(user.id), user.role)
    return TokenResponse(token=token, role=user.role, username=user.username)


@router.post("/register", response_model=TokenResponse)
def register(
    req: RegisterRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("system_admin")),
):
    if req.role not in ROLE_LEVEL:
        raise HTTPException(400, f"Invalid role. Must be one of: {list(ROLE_LEVEL.keys())}")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(409, "Username already exists")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(str(user.id), user.role)
    logger.info("User registered: %s role=%s by admin=%s", user.username, user.role, admin.username)
    return TokenResponse(token=token, role=user.role, username=user.username)
