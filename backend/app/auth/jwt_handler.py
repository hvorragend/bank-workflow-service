"""JWT-Erzeugung und -Validierung fuer Access- und Refresh-Token.

Tokens sind selbst-tragend (HS256, signiert mit JWT_SECRET). Phase-1-Beschraenkung:
keine serverseitige Revokation; Logout invalidiert nur den Refresh-Cookie. Eine
DB-basierte Blacklist kommt in Phase 3 zusammen mit der Schluesselrotation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt

from .config import get_settings
from .schemas import AuthenticatedUser

TokenType = Literal["access", "refresh"]


def _issue_token(user: AuthenticatedUser, token_type: TokenType, lifetime: timedelta) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.username,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
        "auth_source": user.auth_source,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


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

    Raises:
        jwt.PyJWTError bei ungueltiger Signatur, abgelaufenem oder falschem Typ.
    """
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Falscher Token-Typ: erwartet '{expected_type}', erhalten '{payload.get('type')}'."
        )
    user = AuthenticatedUser(
        username=payload["sub"],
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        roles=list(payload.get("roles", [])),
        auth_source=payload.get("auth_source", "local"),
    )
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return user, exp
