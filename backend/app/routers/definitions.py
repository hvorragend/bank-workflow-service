"""Endpoints for FormDefinitions (the versioned templates).

Mit Commit 2: Schreibvorgaenge (POST, activate) erfordern die Rolle 'Admin'.
Die GET-Endpunkte bleiben oeffentlich lesbar — sie liefern keine Antragsdaten,
nur die Maskendefinitionen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth.dependencies import require_role
from ..auth.schemas import AuthenticatedUser
from ..database import get_db

router = APIRouter(prefix="/definitions", tags=["definitions"])


@router.post("", response_model=schemas.FormDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_definition(
    payload: schemas.FormDefinitionCreate,
    db: Session = Depends(get_db),
    _admin: AuthenticatedUser = Depends(require_role("Admin")),
) -> models.FormDefinition:
    """Create a new form definition (status starts as 'draft')."""
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
    db.commit()
    db.refresh(definition)
    return definition


@router.get("", response_model=list[schemas.FormDefinitionOut])
def list_definitions(
    typ: str | None = None,
    nur_aktiv: bool = False,
    db: Session = Depends(get_db),
) -> list[models.FormDefinition]:
    stmt = select(models.FormDefinition)
    if typ:
        stmt = stmt.where(models.FormDefinition.typ == typ)
    if nur_aktiv:
        stmt = stmt.where(models.FormDefinition.status == "active")
    return list(db.scalars(stmt).all())


@router.get("/{definition_id}", response_model=schemas.FormDefinitionOut)
def get_definition(definition_id: str, db: Session = Depends(get_db)) -> models.FormDefinition:
    d = db.get(models.FormDefinition, definition_id)
    if not d:
        raise HTTPException(404, "Definition nicht gefunden.")
    return d


@router.post("/{definition_id}/activate", response_model=schemas.FormDefinitionOut)
def activate(
    definition_id: str,
    db: Session = Depends(get_db),
    _admin: AuthenticatedUser = Depends(require_role("Admin")),
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
