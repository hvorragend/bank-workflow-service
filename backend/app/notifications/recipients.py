"""Backwards-Kompat-Wrapper. Echte Logik liegt in config_service.role_emails.

O-010: Dieses Modul wird vom Produktivcode nicht mehr aufgerufen (nur noch von
tests/test_notifications.py::test_emails_for_role_uses_db_users). Es wird
bewusst NICHT entfernt, um die oeffentliche Kompat-Signatur und den Test stabil
zu halten — reines Aufraeumen waere hier hoeheres Risiko als Nutzen.
"""
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
