"""Geteilte Helfer fuer alle Admin-Sub-Router."""
from __future__ import annotations

import os

from fastapi import Request

from .. import audit, models
from ..auth.schemas import AuthenticatedUser

# X-Forwarded-For ist client-setzbar und darf nur dann vertraut werden, wenn ein
# vorgeschalteter Reverse-Proxy den Header kontrolliert. Bevorzugt wird uvicorn
# mit --proxy-headers gestartet — dann steht die echte Client-IP bereits in
# request.client.host und wir muessen XFF gar nicht parsen. Nur wenn explizit
# TRUST_PROXY_HEADERS=1 gesetzt ist (und uvicorn KEIN --proxy-headers macht),
# werten wir XFF selbst aus. Sonst wuerde ein Angreifer die Audit-Spur faelschen.
_TRUST_XFF = os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes"}


def client_ip(request: Request) -> str | None:
    if _TRUST_XFF:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def audit_admin(db, *, action: str, actor: str, target_type: str | None,
                target_id: str | None, ip: str | None, payload: dict | None = None) -> None:
    audit.write_event(
        db,
        kategorie="admin_config",
        action=action,
        akteur=actor,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        payload=payload,
        commit=False,
    )


def role_to_out(role: models.Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permission_codes": sorted(p.code for p in role.permissions),
    }


def user_to_out(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "auth_source": user.auth_source,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "roles": sorted(r.name for r in user.roles),
    }
