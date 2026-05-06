"""JWT-Erzeugung und -Validierung fuer Access- und Refresh-Token.

Tokens sind selbst-tragend (HS256). Schluesselrotation (Phase 3 / Commit 10):
- Sign mit dem ersten Secret aus jwt_secret_keys()
- Verify probiert alle bekannten Secrets durch — alte Tokens bleiben gueltig,
  bis sie ablaufen
- Logout invalidiert weiterhin nur den Refresh-Cookie; eine echte Token-
  Blacklist gehoert in eine spaetere Operations-Phase
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt

from .config import get_settings, jwt_secret_keys
from .schemas import AuthenticatedUser

TokenType = Literal["access", "refresh"]


def _sign_key() -> str:
    s = get_settings()
    keys = jwt_secret_keys(s)
    if not keys:
        raise RuntimeError("Kein JWT-Secret konfiguriert.")
    return keys[0]


def _issue_token(user: AuthenticatedUser, token_type: TokenType, lifetime: timedelta) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.username,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
        "permissions": user.permissions,
        "auth_source": user.auth_source,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, _sign_key(), algorithm=s.jwt_algorithm)


def issue_access_token(user: AuthenticatedUser) -> tuple[str, int]:
    """Liefert (token, lifetime_seconds)."""
    s = get_settings()
    lifetime = timedelta(minutes=s.jwt_access_lifetime_minutes)
    return _issue_token(user, "access", lifetime), int(lifetime.total_seconds())


def issue_refresh_token(user: AuthenticatedUser) -> tuple[str, int]:
    s = get_settings()
    lifetime = timedelta(hours=s.jwt_refresh_lifetime_hours)
    return _issue_token(user, "refresh", lifetime), int(lifetime.total_seconds())


def decode_token(token: str, expected_type: TokenType) -> tuple[AuthenticatedUser, datetime]:
    """Validiert Signatur, Ablauf und Token-Typ. Gibt (User, exp) zurueck.

    Bei aktivierter Schluesselrotation werden alle bekannten Secrets durchprobiert.
    Wir unterscheiden absichtlich nicht zwischen 'Signatur falsch' und 'Token mit
    altem Key signiert' — beide enden in der gleichen 401-Antwort fuer den User,
    aber alte Keys bleiben akzeptiert, solange sie konfiguriert sind.

    Raises:
        jwt.PyJWTError bei ungueltiger Signatur, abgelaufenem oder falschem Typ.
    """
    s = get_settings()
    keys = jwt_secret_keys(s)
    last_error: jwt.PyJWTError | None = None
    payload: dict[str, Any] | None = None
    for key in keys:
        try:
            payload = jwt.decode(token, key, algorithms=[s.jwt_algorithm])
            last_error = None
            break
        except jwt.ExpiredSignatureError:
            # Abgelaufen ist abgelaufen — Schluesselwechsel hilft hier nicht.
            raise
        except jwt.InvalidSignatureError as e:
            last_error = e
            continue
        except jwt.PyJWTError as e:
            # Andere Fehler (z. B. malformed) sofort durchreichen.
            raise
    if payload is None:
        # Kein Schluessel hat gepasst — letzten Fehler hochreichen.
        raise last_error or jwt.InvalidTokenError("Token konnte mit keinem konfigurierten Schluessel verifiziert werden.")

    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Falscher Token-Typ: erwartet '{expected_type}', erhalten '{payload.get('type')}'."
        )
    user = AuthenticatedUser(
        username=payload["sub"],
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        roles=list(payload.get("roles", [])),
        permissions=list(payload.get("permissions", [])),
        auth_source=payload.get("auth_source", "local"),
    )
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return user, exp
