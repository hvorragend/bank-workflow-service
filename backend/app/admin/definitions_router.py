"""Admin-Endpunkte fuer Workflow-Definitionen (Upload, Diff, Lifecycle).

Bisher in admin/router.py — jetzt rausgespalten und auf require_permission migriert.
Mit der DAG-Erweiterung kommt der grafische Designer hinzu: Definitionen werden
als JSON-Graph ODER als BPMN-XML akzeptiert; in beiden Faellen laeuft die
Persistenz durch den gleichen Validator (`workflow_graph.validate_graph`).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models, workflow_graph
from .. import schemas as core_schemas
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..reporting.security import generate_token, hash_token
from ._helpers import client_ip
from .bpmn import BpmnImportError, parse_bpmn_to_graph
from .diff import diff_schemas, summarize

router = APIRouter(prefix="/admin", tags=["admin:definitions"])

MAX_SCHEMA_BYTES = 256 * 1024
MAX_BPMN_BYTES = 1 * 1024 * 1024  # 1 MB — Diagramme inkl. DI-Layout.


def _known_role_names(db: Session) -> list[str]:
    """Rollen, die im Designer-/BPMN-Validator als 'bekannt' gelten.

    Entspricht 1:1 der Liste, die /admin/roles ausliefert — gespeichert
    in `roles.name` (siehe roles_router.list_roles).
    """
    return list(db.scalars(select(models.Role.name).order_by(models.Role.name)).all())


# ---------- Workflow-Graph-Validierung (Dry-Run) ----------

@router.post("/definitions/validate-graph")
def validate_graph_dryrun(
    payload: dict,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("definitions.upload")),
) -> dict:
    """Validiert einen Workflow-Graph ohne ihn zu speichern. Gibt 200 mit
    `{ok: true}` zurueck oder 422 mit dem Fehlertext.

    Der Designer ruft das beim "Validieren"-Klick auf, um Knoten/Kanten-Fehler
    sofort anzuzeigen, statt einen Upload zu verbrennen."""
    graph = payload.get("workflow_graph")
    if not isinstance(graph, dict):
        raise HTTPException(400, "Feld 'workflow_graph' (Objekt) fehlt im Body.")
    try:
        workflow_graph.validate_graph(graph, known_roles=_known_role_names(db))
    except workflow_graph.GraphError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}


# ---------- Workflow-Upload (JSON-Graph) ----------

@router.post(
    "/definitions/upload",
    response_model=core_schemas.FormDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_definition(
    request: Request,
    typ: str = Form(..., description="Form-Typ, z. B. AT_8_2_Analyse"),
    version: str = Form(..., description="SemVer-Version, z. B. 3.0.0"),
    titel: str = Form(..., description="Anzeigename"),
    workflow_graph_json: str = Form(
        ...,
        alias="workflow_graph",
        description='JSON-Objekt {nodes:[...], edges:[...]} des Workflow-DAG',
    ),
    json_schema: UploadFile = File(...),
    ui_schema: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("definitions.upload")),
) -> models.FormDefinition:
    """Laedt ein neues FormDefinition-Paket hoch und legt es als 'draft' an."""
    js, ui = await _load_schema_pair(json_schema, ui_schema)
    try:
        graph = json.loads(workflow_graph_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"workflow_graph ist kein gueltiges JSON: {e}") from e
    try:
        workflow_graph.validate_graph(graph, known_roles=_known_role_names(db))
    except workflow_graph.GraphError as e:
        raise HTTPException(422, f"workflow_graph ungueltig: {e}") from e

    return _persist_definition(
        db=db, request=request, user=user,
        typ=typ, version=version, titel=titel,
        json_schema=js, ui_schema=ui, graph=graph,
        audit_payload={"typ": typ, "version": version, "titel": titel, "source": "json"},
    )


# ---------- Workflow-Upload (BPMN-XML-Fallback) ----------

@router.post(
    "/definitions/upload-bpmn",
    response_model=core_schemas.FormDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_definition_bpmn(
    request: Request,
    typ: str = Form(...),
    version: str = Form(...),
    titel: str = Form(...),
    json_schema: UploadFile = File(...),
    ui_schema: UploadFile = File(...),
    bpmn_xml: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("definitions.upload")),
) -> models.FormDefinition:
    """Wie /definitions/upload, aber statt JSON-Graph wird ein BPMN-XML akzeptiert.
    Der Server parsed mit defusedxml, mappt das akzeptierte Subset auf den DAG
    und ruft danach den gleichen Validator wie der JSON-Pfad."""
    js, ui = await _load_schema_pair(json_schema, ui_schema)
    bpmn_bytes = await bpmn_xml.read()
    if len(bpmn_bytes) > MAX_BPMN_BYTES:
        raise HTTPException(413, f"BPMN-Datei ueberschreitet {MAX_BPMN_BYTES // 1024} KB.")

    try:
        graph = parse_bpmn_to_graph(bpmn_bytes)
    except BpmnImportError as e:
        raise HTTPException(422, f"BPMN-Import fehlgeschlagen: {e}") from e
    try:
        workflow_graph.validate_graph(graph, known_roles=_known_role_names(db))
    except workflow_graph.GraphError as e:
        raise HTTPException(422, f"BPMN ergibt keinen gueltigen Workflow-Graph: {e}") from e

    return _persist_definition(
        db=db, request=request, user=user,
        typ=typ, version=version, titel=titel,
        json_schema=js, ui_schema=ui, graph=graph,
        audit_payload={"typ": typ, "version": version, "titel": titel,
                       "bpmn_bytes": len(bpmn_bytes), "source": "bpmn"},
    )


async def _load_schema_pair(json_schema: UploadFile, ui_schema: UploadFile) -> tuple[dict, dict]:
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
    return js, ui


def _persist_definition(
    *, db: Session, request: Request, user: AuthenticatedUser,
    typ: str, version: str, titel: str,
    json_schema: dict, ui_schema: dict, graph: dict,
    audit_payload: dict,
) -> models.FormDefinition:
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
        json_schema=json_schema, ui_schema=ui_schema,
        workflow_graph=graph,
        status="draft", erstellt_von=user.username,
    )
    db.add(d)
    db.flush()
    audit.write_event(
        db, kategorie="definition", action="definition.uploaded",
        akteur=user.username, target_type="FormDefinition", target_id=d.id,
        ip=client_ip(request),
        payload=audit_payload, commit=False,
    )
    db.commit()
    db.refresh(d)
    return d


# ---------- Diff ----------

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


# ---------- Retire ----------

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
    d.gueltig_bis = datetime.now(UTC)
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
    tok.revoked_at = datetime.now(UTC)
    audit.write_event(
        db, kategorie="admin_config", action="reporting_token.revoked",
        akteur=user.username, target_type="ApiToken", target_id=tok.id,
        ip=client_ip(request),
        payload={"name": tok.name},
        commit=False,
    )
    db.commit()
