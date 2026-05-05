"""Backwards-Kompat-Wrapper. Echte Logik liegt in config_service.role_emails."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config_service.role_emails import email_for_user as _email_for_user
from ..config_service.role_emails import emails_for_role as _emails_for_role
from ..database import SessionLocal


def emails_for_role(role: str, db: Session | None = None) -> list[str]:
    if db is not None:
        return _emails_for_role(db, role)
    with SessionLocal() as s:
        return _emails_for_role(s, role)


def email_for_user(username: str, db: Session | None = None) -> str | None:
    if db is not None:
        return _email_for_user(db, username)
    with SessionLocal() as s:
        return _email_for_user(s, username)
