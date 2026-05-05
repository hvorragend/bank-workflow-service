"""Admin-Audit-Log-Endpunkte."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db

router = APIRouter(prefix="/admin/audit", tags=["admin:audit"])


@router.get("")
def list_audit_events(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.audit.read")),
    kategorie: str | None = Query(None, description="Filter Kategorie (auth, definition, instance, admin_config)"),
    akteur: str | None = Query(None, description="Filter auf Username"),
    seit: datetime | None = Query(None, description="Erst ab diesem Zeitpunkt"),
    limit: int = Query(200, ge=1, le=1000),
    sort: Literal["desc", "asc"] = Query("desc"),
) -> list[dict]:
    stmt = select(models.AuditEvent)
    if kategorie:
        stmt = stmt.where(models.AuditEvent.kategorie == kategorie)
    if akteur:
        stmt = stmt.where(models.AuditEvent.akteur == akteur)
    if seit:
        stmt = stmt.where(models.AuditEvent.zeitstempel >= seit)
    if sort == "asc":
        stmt = stmt.order_by(models.AuditEvent.zeitstempel.asc())
    else:
        stmt = stmt.order_by(models.AuditEvent.zeitstempel.desc())
    stmt = stmt.limit(limit)
    events = list(db.scalars(stmt).all())
    return [
        {
            "id":          e.id,
            "zeitstempel": e.zeitstempel,
            "kategorie":   e.kategorie,
            "action":      e.action,
            "akteur":      e.akteur,
            "target_type": e.target_type,
            "target_id":   e.target_id,
            "ip":          e.ip,
            "payload":     e.payload,
        }
        for e in events
    ]
