"""Admin-Audit-Log-Endpunkte."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..routers.instances import _csv_cell

router = APIRouter(prefix="/admin/audit", tags=["admin:audit"])


def _audit_csv(events: list[models.AuditEvent]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, dialect="excel", delimiter=";")
    w.writerow([
        "id", "zeitstempel", "kategorie", "action", "akteur",
        "target_type", "target_id", "ip", "payload",
    ])
    for e in events:
        w.writerow([_csv_cell(v) for v in (
            e.id,
            e.zeitstempel.isoformat() if e.zeitstempel else "",
            e.kategorie,
            e.action,
            e.akteur,
            e.target_type,
            e.target_id,
            e.ip,
            json.dumps(e.payload, ensure_ascii=False) if e.payload is not None else "",
        )])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


@router.get("", response_model=None)
def list_audit_events(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.audit.read")),
    kategorie: str | None = Query(None, description="Filter Kategorie (auth, definition, instance, admin_config)"),
    akteur: str | None = Query(None, description="Filter auf Username"),
    seit: datetime | None = Query(None, description="Erst ab diesem Zeitpunkt"),
    limit: int = Query(200, ge=1, le=1000),
    sort: Literal["desc", "asc"] = Query("desc"),
    format: Literal["json", "csv"] = Query("json"),
) -> list[dict] | Response:
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
    # CSV ist ein Revisions-Export und wird nicht durch `limit` beschnitten;
    # Pagination gilt nur fuer die JSON-Ansicht im Admin-Panel.
    if format == "csv":
        return _audit_csv(list(db.scalars(stmt).all()))
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
