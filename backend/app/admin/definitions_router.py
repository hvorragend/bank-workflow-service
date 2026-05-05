"""Admin-Endpunkte fuer Workflow-Definitionen (Upload, Diff, Lifecycle).

Bisher in admin/router.py — jetzt rausgespalten und auf require_permission migriert.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models, schemas as core_schemas
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..reporting.security import generate_token, hash_token
from ._helpers import client_ip
from .diff import diff_schemas, summarize

router = APIRouter(prefix="/admin", tags=["admin:definitions"])

MAX_SCHEMA_BYTES = 256 * 1024


@router.post(
    "/definitions/upload",
    response_model=core_schemas.FormDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_definition(
    request: Request,
    typ: str = Form(...),
    version: str = Form(...),
    titel: str = Form(...),
    workflow_stages: str = Form(...),
    json_schema: UploadFile = File(...),
    ui_schema: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("definitions.upload")),
) -> models.FormDefinition:
    js_bytes = await json_schema.read()
    ui_bytes = await ui_schema.read()
    if len(js_bytes) > MAX_SCHEMA_BYTES or len(ui_bytes) > MAX_SCHEMA_BYTES:
        raise HTTPException(413, f"Schema-Datei ueberschreitet {MAX_SCHEMA_BYTES // 1024} KB.")

    try:
        js = json.loads(js_bytes)
        ui = json.loads(ui_bytes)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Ungueltiges JSON: {e}") from e

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

    existing = db.scalar(
        select(models.FormDefinition).where(
            models.FormDefinition.typ == typ,
            models.FormDefinition.version == version,
        )
    )
    if existing:
        raise HTTPException(409, f"Definition {typ}/{version} existiert bereits.")

    d = models.FormDefinition(
        typ=typ, version=version, titel=titel,
        json_schema=js, ui_schema=ui, workflow_stages=stages,
        status="draft", erstellt_von=user.username,
    )
    db.add(d)
    db.flush()
    audit.write_event(
        db, kategorie="definition", action="definition.uploaded",
        akteur=user.username, target_type="FormDefinition", target_id=d.id,
        ip=client_ip(request),
        payload={"typ": typ, "version": version, "titel": titel,
                 "json_schema_bytes": len(js_bytes), "ui_schema_bytes": len(ui_bytes)},
        commit=False,
    )
    db.commit()
    db.refresh(d)
    return d


@router.get("/definitions/{a_id}/diff/{b_id}")
def diff_definitions(
    a_id: str, b_id: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("definitions.diff")),
) -> dict:
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


@router.post("/definitions/{definition_id}/retire", response_model=core_schemas.FormDefinitionOut)
def retire(
    definition_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("definitions.retire")),
) -> models.FormDefinition:
    d = db.get(models.FormDefinition, definition_id)
    if not d:
        raise HTTPException(404, "Definition nicht gefunden.")
    if d.status != "active":
        raise HTTPException(409, f"Nur aktive Definitionen koennen retired werden (aktuell: {d.status}).")
    d.status = "retired"
    d.gueltig_bis = datetime.now(timezone.utc)
    audit.write_event(
        db, kategorie="definition", action="definition.retired",
        akteur=user.username, target_type="FormDefinition", target_id=d.id,
        ip=client_ip(request),
        payload={"typ": d.typ, "version": d.version},
        commit=False,
    )
    db.commit()
    db.refresh(d)
    return d


# ---------- Reporting-Tokens (waren bisher in admin/router.py) ----------

@router.post("/reporting-tokens", status_code=201)
def create_reporting_token(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.api_tokens.write")),
) -> dict:
    name = (payload or {}).get("name")
    if not name:
        raise HTTPException(400, "Feld 'name' ist Pflicht.")
    expires_iso = (payload or {}).get("expires_at")
    expires_at = None
    if expires_iso:
        try:
            expires_at = datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(400, f"expires_at ungueltig: {e}") from e
    raw = generate_token()
    tok = models.ApiToken(
        token_hash=hash_token(raw), name=name, scopes=["reporting:read"],
        created_by=user.username, expires_at=expires_at,
    )
    db.add(tok)
    audit.write_event(
        db, kategorie="admin_config", action="reporting_token.created",
        akteur=user.username, target_type="ApiToken", target_id=tok.id,
        ip=client_ip(request),
        payload={"name": name, "expires_at": expires_iso},
        commit=False,
    )
    db.commit()
    db.refresh(tok)
    return {
        "id": tok.id, "name": tok.name, "scopes": tok.scopes,
        "created_at": tok.created_at, "expires_at": tok.expires_at,
        "token": raw,
        "_warning": "Dieser Token ist NUR EINMAL sichtbar. Bitte sicher aufbewahren.",
    }


@router.get("/reporting-tokens")
def list_reporting_tokens(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.api_tokens.read")),
) -> list[dict]:
    rows = list(db.scalars(select(models.ApiToken).order_by(models.ApiToken.created_at.desc())).all())
    return [
        {
            "id": t.id, "name": t.name, "scopes": t.scopes,
            "created_at": t.created_at, "created_by": t.created_by,
            "expires_at": t.expires_at, "last_used_at": t.last_used_at,
            "revoked_at": t.revoked_at,
        }
        for t in rows
    ]


@router.delete("/reporting-tokens/{token_id}", status_code=204)
def revoke_reporting_token(
    token_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.api_tokens.write")),
):
    tok = db.get(models.ApiToken, token_id)
    if not tok:
        raise HTTPException(404, "Token nicht gefunden.")
    if tok.revoked_at:
        return
    tok.revoked_at = datetime.now(timezone.utc)
    audit.write_event(
        db, kategorie="admin_config", action="reporting_token.revoked",
        akteur=user.username, target_type="ApiToken", target_id=tok.id,
        ip=client_ip(request),
        payload={"name": tok.name},
        commit=False,
    )
    db.commit()
