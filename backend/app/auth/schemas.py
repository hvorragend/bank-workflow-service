"""Pydantic-Schemas fuer die Auth-API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=512)


class TokenResponse(BaseModel):
    """Antwort auf POST /auth/login und /auth/refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Lebensdauer des Access-Tokens in Sekunden")


class AuthenticatedUser(BaseModel):
    """Eine eingeloggte Identitaet — Ergebnis der Token-Validierung."""

    username: str
    name: str = ""
    email: str = ""
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(
        default_factory=list,
        description="Aufgeloeste Permissions aus den zugewiesenen Rollen — werden im JWT mitgegeben.",
    )
    auth_source: str = "local"  # local | ldap | emergency


class MeResponse(AuthenticatedUser):
    """GET /auth/me — Identitaet plus Token-Ablauf, damit Clients Session-UX bauen koennen."""

    token_expires_at: datetime
