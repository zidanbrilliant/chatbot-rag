"""Seed initial admin user on startup from env vars.

Ponytail: env-driven, idempotent — safe to re-run on every container start.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth import hash_password

logger = logging.getLogger("chatbot")


def seed_admin_user(db: Session) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        logger.info("Admin user '%s' already exists — skipping seed", username)
        return
    user = User(
        username=username,
        password_hash=hash_password(password),
        role="system_admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    logger.warning("Seeded admin user '%s' (CHANGE PASSWORD IN PROD). Role=system_admin", username)
