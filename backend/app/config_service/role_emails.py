"""Aufloesung Rolle -> E-Mail-Empfaenger.

Reihenfolge:
1. Eintraege aus role_emails (z. B. Gruppenpostfach Vorstand@vbga.de)
2. PLUS alle aktiven User mit der Rolle, die eine email-Adresse haben

Duplikate werden entfernt; Reihenfolge bleibt stabil (Gruppenpostfach zuerst).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


def emails_for_role(db: Session, role_name: str) -> list[str]:
    role = db.scalar(select(models.Role).where(models.Role.name == role_name))
    if not role:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def _add(addr: str | None) -> None:
        a = (addr or "").strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)

    # Gruppenpostfaecher
    for addr in db.scalars(
        select(models.RoleEmail.email).where(models.RoleEmail.role_id == role.id)
    ).all():
        _add(addr)

    # User mit dieser Rolle
    role_users = db.execute(
        select(models.User.username, models.User.email)
        .join(models.UserRole, models.UserRole.user_id == models.User.id)
        .where(
            models.UserRole.role_id == role.id,
            models.User.is_active.is_(True),
        )
    ).all()
    for _username, addr in role_users:
        _add(addr)

    # N-001: aktive Vertreter der Rolleninhaber ergaenzen.
    usernames = [u for u, _ in role_users]
    if usernames:
        today = date.today()
        deputies = db.scalars(
            select(models.Delegation.to_username).where(
                models.Delegation.from_username.in_(usernames),
                models.Delegation.von_datum <= today,
                models.Delegation.bis_datum >= today,
            )
        ).all()
        for deputy in deputies:
            user = db.scalar(select(models.User).where(models.User.username == deputy))
            if user and user.is_active and user.email:
                _add(user.email)
    return out


def email_for_user(db: Session, username: str) -> str | None:
    user = db.scalar(select(models.User).where(models.User.username == username))
    if not user or not user.email:
        return None
    return user.email
