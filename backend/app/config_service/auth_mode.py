"""Runtime-Auth-Konfiguration aus app_settings: Auth-Modus + Login-Rate-Limit."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from .. import models

AuthMode = Literal["local", "ldap", "both"]


def get_auth_mode(db: Session) -> AuthMode:
    row = db.get(models.AppSetting, "auth.mode")
    value = (row.value if row else "local").strip()
    if value not in ("local", "ldap", "both"):
        return "local"
    return value  # type: ignore[return-value]


def set_auth_mode(db: Session, mode: AuthMode, *, actor: str) -> None:
    if mode not in ("local", "ldap", "both"):
        raise ValueError(f"Unbekannter Auth-Modus: {mode!r}")
    row = db.get(models.AppSetting, "auth.mode")
    if row:
        row.value = mode
        row.updated_by = actor
    else:
        db.add(models.AppSetting(key="auth.mode", value=mode, updated_by=actor))


def get_login_rate_limit(db: Session) -> str:
    row = db.get(models.AppSetting, "auth.login_rate_limit")
    return (row.value if row else "5/minute").strip() or "5/minute"


def set_login_rate_limit(db: Session, value: str, *, actor: str) -> None:
    if not value.strip():
        raise ValueError("Rate-Limit darf nicht leer sein.")
    row = db.get(models.AppSetting, "auth.login_rate_limit")
    if row:
        row.value = value.strip()
        row.updated_by = actor
    else:
        db.add(models.AppSetting(key="auth.login_rate_limit", value=value.strip(), updated_by=actor))
