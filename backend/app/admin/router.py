"""Admin-Endpunkte: Workflow-Upload, Diff zwischen Versionen, Audit-Log-Einsicht.

Alle Routen unter /admin/* erfordern die Rolle 'Admin' (siehe require_role).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models, schemas
from ..auth.dependencies import require_role
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from .diff import diff_schemas, summarize

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_SCHEMA_BYTES = 256 * 1024  # 256 KB pro Schema-File — JSON-Schemas sind klein.


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------- Workflow-Upload ----------

@router.post(
    "/definitions/upload",
    response_model=schemas.FormDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_definition(
    request: Request,
    typ: str = Form(..., description="Form-Typ, z. B. AT_8_2_Analyse"),
    version: str = Form(..., description="SemVer-Version, z. B. 3.0.0"),
    titel: str = Form(..., description="Anzeigename"),
    workflow_stages: str = Form(
        ...,
        description='JSON-Array der Stages, z. B. \'[{"name":"fb","rolle":"Fachbereichsleiter"}]\'',
    ),
    json_schema: UploadFile = File(...),
    ui_schema: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("Admin")),
) -> models.FormDefinition:
    """Laedt ein neues FormDefinition-Paar hoch und legt es als 'draft' an.

    Das aktive Schalten erfolgt anschliessend separat ueber /definitions/{id}/activate
    — bewusst zweistufig, damit ein Admin das Schema vorab inspizieren kann.
    """
    js_bytes = await json_schema.read()
    ui_bytes = await ui_schema.read()
    if len(js_bytes) > MAX_SCHEMA_BYTES or len(ui_bytes) > MAX_SCHEMA_BYTES:
        raise HTTPException(413, f"Schema-Datei ueberschreitet {MAX_SCHEMA_BYTES // 1024} KB.")

    try:
        js = json.loads(js_bytes)
        ui = json.loads(ui_bytes)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Ungueltiges JSON: {e}") from e

    # Draft-2020-12-Konformitaet pruefen — fail loudly bevor wir persistieren.
    try:
        Draft202012Validator.check_schema(js)
    except SchemaError as e:
        raise HTTPException(422, f"json_schema ist kein gueltiges Draft-2020-12-Schema: {e.message}") from e

    try:
        stages = json.loads(workflow_stages)
        if not isinstance(stages, list) or not stages:
            raise ValueError("workflow_stages muss eine nicht-leere Liste sein.")
        for s in stages:
            if not isinstance(s, dict) or "name" not in s or "rolle" not in s:
                raise ValueError("Jede Stage braucht Felder 'name' und 'rolle'.")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"workflow_stages ungueltig: {e}") from e

    # Bestehende Version desselben Typs duplizieren wir nicht.
    existing = db.scalar(
        select(models.FormDefinition).where(
            models.FormDefinition.typ == typ,
            models.FormDefinition.version == version,
        )
    )
    if existing:
        raise HTTPException(409, f"Definition {typ}/{version} existiert bereits.")

    d = models.FormDefinition(
        typ=typ,
        version=version,
        titel=titel,
        json_schema=js,
        ui_schema=ui,
        workflow_stages=stages,
        status="draft",
        erstellt_von=user.username,
    )
    db.add(d)
    db.flush()

    audit.write_event(
        db,
        kategorie="definition",
        action="definition.uploaded",
        akteur=user.username,
        target_type="FormDefinition",
        target_id=d.id,
        ip=_client_ip(request),
        payload={"typ": typ, "version": version, "titel": titel,
                 "json_schema_bytes": len(js_bytes), "ui_schema_bytes": len(ui_bytes)},
        commit=False,
    )
    db.commit()
    db.refresh(d)
    return d


# ---------- Schema-Diff ----------

@router.get("/definitions/{a_id}/diff/{b_id}")
def diff_definitions(
    a_id: str,
    b_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("Admin")),
) -> dict:
    """Vergleicht zwei FormDefinitions und liefert eine Liste struktureller Aenderungen."""
    a = db.get(models.FormDefinition, a_id)
    b = db.get(models.FormDefinition, b_id)
    if not a or not b:
        raise HTTPException(404, "Mindestens eine Definition nicht gefunden.")
    diffs = diff_schemas(a.json_schema, b.json_schema)
    return {
        "from": {"id": a.id, "typ": a.typ, "version": a.version},
        "to":   {"id": b.id, "typ": b.typ, "version": b.version},
        "diffs": diffs,
        "summary": summarize(diffs),
    }


# ---------- Definition-Lifecycle (mit Audit) ----------

@router.post("/definitions/{definition_id}/retire", response_model=schemas.FormDefinitionOut)
def retire(
    definition_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("Admin")),
) -> models.FormDefinition:
    """Setzt eine aktive Definition auf 'retired'. Anschliessend werden keine
    neuen Antraege mehr gegen sie zugelassen — Altantraege bleiben sichtbar."""
    d = db.get(models.FormDefinition, definition_id)
    if not d:
        raise HTTPException(404, "Definition nicht gefunden.")
    if d.status != "active":
        raise HTTPException(409, f"Nur aktive Definitionen koennen retired werden (aktuell: {d.status}).")
    d.status = "retired"
    d.gueltig_bis = datetime.utcnow()
    audit.write_event(
        db,
        kategorie="definition",
        action="definition.retired",
        akteur=user.username,
        target_type="FormDefinition",
        target_id=d.id,
        ip=_client_ip(request),
        payload={"typ": d.typ, "version": d.version},
        commit=False,
    )
    db.commit()
    db.refresh(d)
    return d


# ---------- Audit-Log ----------

@router.get("/audit")
def list_audit_events(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("Admin")),
    kategorie: str | None = Query(None, description="Filter Kategorie (auth, definition, instance, admin)"),
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
