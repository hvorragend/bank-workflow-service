"""Lese-only Reporting-Endpunkte fuer Aufsicht/Revision.

Authentifizierung via API-Token (siehe security.py), separater Scope
`reporting:read`. Endpunkte liefern aggregierte oder vollstaendige Daten,
schreiben aber nichts — und werden bewusst getrennt vom interaktiven
JWT-Login gehalten, damit kompromittierte User-Sessions hier nicht
hereinkommen.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from .security import require_reporting_token

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/instances/{instance_id}")
def get_full_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    _token = Depends(require_reporting_token),
) -> dict[str, Any]:
    """Vollstaendiger Antrag inklusive Approvals und gepinntes Schema —
    fuer Externe Pruefung / Revisionsanforderungen."""
    inst = db.get(models.FormInstance, instance_id)
    if not inst:
        raise HTTPException(404, "Antrag nicht gefunden.")
    return {
        "id": inst.id,
        "form_definition_id": inst.form_definition_id,
        "schema": {
            "typ": inst.definition.typ,
            "version": inst.definition.version,
            "json_schema": inst.definition.json_schema,
            "ui_schema": inst.definition.ui_schema,
            "workflow_graph": inst.definition.workflow_graph,
        },
        "daten": inst.daten,
        "antragsteller": inst.antragsteller,
        "status": inst.status,
        "erstellt_am": inst.erstellt_am.isoformat() if inst.erstellt_am else None,
        "abgeschlossen_am": inst.abgeschlossen_am.isoformat() if inst.abgeschlossen_am else None,
        "active_stages": [
            {
                "node_id": a.node_id, "rolle": a.rolle,
                "eingetreten_am": a.eingetreten_am.isoformat() if a.eingetreten_am else None,
            }
            for a in inst.active_stages
        ],
        "approvals": [
            {
                "stage": a.stage, "rolle": a.rolle, "genehmiger": a.genehmiger,
                "entscheidung": a.entscheidung, "kommentar": a.kommentar,
                "zeitstempel": a.zeitstempel.isoformat(),
            }
            for a in inst.approvals
        ],
    }


@router.get("/aggregates/quarterly")
def quarterly_counts(
    db: Session = Depends(get_db),
    _token = Depends(require_reporting_token),
) -> list[dict[str, Any]]:
    """Anzahl Antraege pro Quartal, gruppiert nach Typ und Status."""
    instances = list(db.scalars(select(models.FormInstance)).all())
    buckets: dict[tuple[int, int, str, str], int] = {}
    for i in instances:
        if not i.erstellt_am:
            continue
        q = (i.erstellt_am.month - 1) // 3 + 1
        key = (i.erstellt_am.year, q, i.definition.typ, i.status)
        buckets[key] = buckets.get(key, 0) + 1
    return [
        {"jahr": y, "quartal": q, "typ": t, "status": s, "anzahl": n}
        for (y, q, t, s), n in sorted(buckets.items())
    ]


@router.get("/aggregates/duration")
def duration_per_typ(
    db: Session = Depends(get_db),
    _token = Depends(require_reporting_token),
) -> list[dict[str, Any]]:
    """Durchschnittliche Bearbeitungsdauer pro Typ (genehmigte Antraege)."""
    decided = list(
        db.scalars(
            select(models.FormInstance).where(models.FormInstance.status == "genehmigt")
        ).all()
    )
    by_typ: dict[str, list[float]] = {}
    for i in decided:
        if not (i.erstellt_am and i.abgeschlossen_am):
            continue
        days = (i.abgeschlossen_am - i.erstellt_am).total_seconds() / 86400.0
        by_typ.setdefault(i.definition.typ, []).append(days)
    return [
        {
            "typ": t,
            "anzahl": len(days),
            "avg_days": round(sum(days) / len(days), 2) if days else None,
            "min_days": round(min(days), 2) if days else None,
            "max_days": round(max(days), 2) if days else None,
        }
        for t, days in sorted(by_typ.items())
    ]
