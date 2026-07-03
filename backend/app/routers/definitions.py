"""Endpoints for FormDefinitions (the versioned templates).

Mit Commit 2: Schreibvorgaenge (POST, activate) erfordern die Rolle 'Admin'.
F-042: Auch die GET-Endpunkte erfordern jetzt Authentifizierung und die
Permission 'definitions.read' — sie liefern zwar keine Antragsdaten, aber die
Maskendefinitionen (inkl. Workflow-Graph) sollen nicht anonym abrufbar sein.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas, workflow_graph
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db

router = APIRouter(prefix="/definitions", tags=["definitions"])


def _known_role_names(db: Session) -> list[str]:
    return list(db.scalars(select(models.Role.name)).all())


def _validate_definition_payload(payload: schemas.FormDefinitionCreate, db: Session) -> None:
    """Dieselbe Eingangsvalidierung wie im Admin-Upload (F-007): kaputtes
    JSON-Schema oder ein ungueltiger/zyklischer Workflow-Graph wuerde sonst
    persistiert und erst zur Laufzeit als 500 bzw. RecursionError knallen."""
    try:
        Draft202012Validator.check_schema(payload.json_schema)
    except SchemaError as e:
        raise HTTPException(422, f"Ungueltiges JSON-Schema: {e.message}")
    try:
        workflow_graph.validate_graph(payload.workflow_graph, known_roles=_known_role_names(db))
    except workflow_graph.GraphError as e:
        raise HTTPException(422, f"Ungueltiger Workflow-Graph: {e}")


@router.post("", response_model=schemas.FormDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_definition(
    payload: schemas.FormDefinitionCreate,
    db: Session = Depends(get_db),
    _admin: AuthenticatedUser = Depends(require_permission("definitions.upload")),
) -> models.FormDefinition:
    """Create a new form definition (status starts as 'draft')."""
    _validate_definition_payload(payload, db)
    existing = db.scalar(
        select(models.FormDefinition).where(
            models.FormDefinition.typ == payload.typ,
            models.FormDefinition.version == payload.version,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Definition {payload.typ}/{payload.version} existiert bereits.",
        )
    definition = models.FormDefinition(**payload.model_dump())
    db.add(definition)
    try:
        db.commit()
    except IntegrityError:
        # Race: eine konkurrierende Anlage derselben typ/version hat den
        # Unique-Constraint zuerst belegt -> sauberer 409 statt 500.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Definition {payload.typ}/{payload.version} existiert bereits.",
        )
    db.refresh(definition)
    return definition


@router.get("", response_model=list[schemas.FormDefinitionOut])
def list_definitions(
    typ: str | None = None,
    nur_aktiv: bool = False,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("definitions.read")),
) -> list[models.FormDefinition]:
    stmt = select(models.FormDefinition)
    if typ:
        stmt = stmt.where(models.FormDefinition.typ == typ)
    if nur_aktiv:
        stmt = stmt.where(models.FormDefinition.status == "active")
    return list(db.scalars(stmt).all())


@router.get("/{definition_id}", response_model=schemas.FormDefinitionOut)
def get_definition(
    definition_id: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("definitions.read")),
) -> models.FormDefinition:
    d = db.get(models.FormDefinition, definition_id)
    if not d:
        raise HTTPException(404, "Definition nicht gefunden.")
    return d


@router.post("/{definition_id}/activate", response_model=schemas.FormDefinitionOut)
def activate(
    definition_id: str,
    db: Session = Depends(get_db),
    _admin: AuthenticatedUser = Depends(require_permission("definitions.activate")),
) -> models.FormDefinition:
    """Activate a draft definition. Retires older active versions of the same typ."""
    d = db.get(models.FormDefinition, definition_id)
    if not d:
        raise HTTPException(404, "Definition nicht gefunden.")
    if d.status != "draft":
        raise HTTPException(409, f"Nur Entwürfe können aktiviert werden (aktuell: {d.status}).")

    # Retire any other active version of the same type.
    others = db.scalars(
        select(models.FormDefinition).where(
            models.FormDefinition.typ == d.typ,
            models.FormDefinition.status == "active",
            models.FormDefinition.id != d.id,
        )
    ).all()
    from datetime import datetime, timezone
    for other in others:
        other.status = "retired"
        other.gueltig_bis = datetime.now(timezone.utc)

    d.status = "active"
    db.commit()
    db.refresh(d)
    return d
