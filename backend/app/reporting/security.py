"""Header-Auth fuer Reporting-Endpunkte.

Token kommt als Klartext im `X-Reporting-Token`-Header. Wir hashen ihn mit
SHA-256 und vergleichen gegen die in api_tokens gespeicherten Hashes.
SHA-256 reicht hier, weil der Token bereits hochentropisch ist (>= 32 Bytes
Zufall) — Brute-Force ueber den Hash ist nicht praktikabel.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db


def generate_token() -> str:
    """Erzeugt einen neuen API-Token (Klartext). Der Aufrufer ist verantwortlich
    dafuer, ihn umgehend zu uebergeben — er ist nach diesem Aufruf nicht mehr
    rekonstruierbar."""
    return "bws_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_reporting_token(
    db: Session = Depends(get_db),
    x_reporting_token: str | None = Header(default=None, alias="X-Reporting-Token"),
) -> models.ApiToken:
    if not x_reporting_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Reporting-Token-Header fehlt.",
        )
    digest = hash_token(x_reporting_token)
    tok = db.scalar(select(models.ApiToken).where(models.ApiToken.token_hash == digest))
    if not tok:
        raise HTTPException(401, "API-Token unbekannt.")
    if tok.revoked_at:
        raise HTTPException(401, "API-Token widerrufen.")
    if tok.expires_at and tok.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "API-Token abgelaufen.")
    if "reporting:read" not in (tok.scopes or []):
        raise HTTPException(403, "Token hat nicht den Scope 'reporting:read'.")

    tok.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return tok
