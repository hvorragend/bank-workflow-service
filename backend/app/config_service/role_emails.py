"""Aufloesung Rolle -> E-Mail-Empfaenger.

Reihenfolge:
1. Eintraege aus role_emails (z. B. Gruppenpostfach Vorstand@vbga.de)
2. PLUS alle aktiven User mit der Rolle, die eine email-Adresse haben

Duplikate werden entfernt; Reihenfolge bleibt stabil (Gruppenpostfach zuerst).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


def emails_for_role(db: Session, role_name: str) -> list[str]:
    role = db.scalar(select(models.Role).where(models.Role.name == role_name))
    if not role:
        return []

    out: list[str] = []
    seen: set[str] = set()

    # Gruppenpostfaecher
    for addr in db.scalars(
        select(models.RoleEmail.email).where(models.RoleEmail.role_id == role.id)
    ).all():
        a = (addr or "").strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)

    # User mit dieser Rolle
    user_emails = db.execute(
        select(models.User.email)
        .join(models.UserRole, models.UserRole.user_id == models.User.id)
        .where(
            models.UserRole.role_id == role.id,
            models.User.is_active.is_(True),
            models.User.email.is_not(None),
        )
    ).all()
    for (addr,) in user_emails:
        a = (addr or "").strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def email_for_user(db: Session, username: str) -> str | None:
    user = db.scalar(select(models.User).where(models.User.username == username))
    if not user or not user.email:
        return None
    return user.email
