"""Aufloesung Rolle -> E-Mail-Empfaenger.

Reihenfolge:
1. Wenn config/role_emails.toml einen Eintrag fuer die Rolle hat: nimm den.
2. Sonst: alle local_users, die die Rolle haben, mit nicht-leerer email-Adresse.

(LDAP-Group-Resolver kommt in Phase 3 mit Eskalation, falls noetig — fuer
den Standardfall „Gruppenpostfach pro Rolle" reicht das toml-Mapping.)
"""
from __future__ import annotations

from ..auth.config import load_local_users
from .config import load_role_emails


def emails_for_role(role: str) -> list[str]:
    overrides = load_role_emails()
    if role in overrides:
        return [a.strip() for a in overrides[role] if a.strip()]
    # Fallback: aus local_users
    addrs: list[str] = []
    for user in load_local_users().values():
        if role in user.roles and user.email:
            addrs.append(user.email)
    # Duplikate entfernen, Reihenfolge stabil
    seen: set[str] = set()
    out: list[str] = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def email_for_user(username: str) -> str | None:
    """Liefert die E-Mail eines konkreten Users (Antragstellers, falls bekannt)."""
    user = load_local_users().get(username)
    return user.email if user and user.email else None
