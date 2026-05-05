"""Endpoints for FormInstances (the actual filled-out applications)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, workflow
from ..database import get_db

router = APIRouter(prefix="/instances", tags=["instances"])


@router.get("", response_model=list[schemas.FormInstanceWithSchema])
def list_instances(db: Session = Depends(get_db)):
    """List all instances, newest first."""
    instances = list(
        db.scalars(
            select(models.FormInstance).order_by(models.FormInstance.erstellt_am.desc())
        ).all()
    )
    return [_to_instance_with_schema(i) for i in instances]


def _validate_against_definition(daten: dict, definition: models.FormDefinition) -> None:
    """Validate form data against the JSON schema of the *pinned* definition version."""
    try:
        Draft202012Validator(definition.json_schema).validate(daten)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Validierungsfehler gegen Schema {definition.typ}/{definition.version}: "
                   f"{e.message} (Pfad: {'/'.join(str(p) for p in e.absolute_path)})",
        )


@router.post("", response_model=schemas.FormInstanceWithSchema, status_code=status.HTTP_201_CREATED)
def create_instance(
    payload: schemas.FormInstanceCreate,
    db: Session = Depends(get_db),
):
    """Create a new instance. Pins it to the chosen FormDefinition version forever."""
    definition = db.get(models.FormDefinition, payload.form_definition_id)
    if not definition:
        raise HTTPException(404, "FormDefinition nicht gefunden.")
    if definition.status != "active":
        raise HTTPException(
            409,
            f"FormDefinition {definition.typ}/{definition.version} ist nicht aktiv "
            f"(Status: {definition.status}). Anträge nur gegen aktive Versionen.",
        )

    _validate_against_definition(payload.daten, definition)

    instance = models.FormInstance(
        form_definition_id=definition.id,
        daten=payload.daten,
        antragsteller=payload.antragsteller,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


@router.get("/{instance_id}", response_model=schemas.FormInstanceWithSchema)
def get_instance(instance_id: str, db: Session = Depends(get_db)):
    """Return the instance plus its originally-pinned schema, ready for the UI to render."""
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    # Re-validate on read — guards against schema drift via direct DB writes.
    _validate_against_definition(instance.daten, instance.definition)
    return _to_instance_with_schema(instance)


@router.post("/{instance_id}/submit", response_model=schemas.FormInstanceWithSchema)
def submit_instance(instance_id: str, db: Session = Depends(get_db)):
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    try:
        workflow.submit(instance)
    except workflow.WorkflowError as e:
        raise HTTPException(409, str(e))
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


@router.post("/{instance_id}/decide", response_model=schemas.FormInstanceWithSchema)
def decide_instance(
    instance_id: str,
    action: schemas.ApprovalAction,
    db: Session = Depends(get_db),
):
    """Approve, reject or return an instance at its current stage."""
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    try:
        workflow.decide(
            db, instance,
            genehmiger=action.genehmiger,
            rolle=action.rolle,
            entscheidung=action.entscheidung,
            kommentar=action.kommentar,
        )
    except workflow.WorkflowError as e:
        raise HTTPException(409, str(e))
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


def _to_instance_with_schema(instance: models.FormInstance) -> dict:
    """Build the response payload that bundles instance + pinned schema."""
    return {
        "id": instance.id,
        "form_definition_id": instance.form_definition_id,
        "daten": instance.daten,
        "antragsteller": instance.antragsteller,
        "aktuelle_stage": instance.aktuelle_stage,
        "status": instance.status,
        "erstellt_am": instance.erstellt_am,
        "abgeschlossen_am": instance.abgeschlossen_am,
        "approvals": instance.approvals,
        "json_schema": instance.definition.json_schema,
        "ui_schema": instance.definition.ui_schema,
        "workflow_stages": instance.definition.workflow_stages,
        "schema_version": f"{instance.definition.typ}/{instance.definition.version}",
    }
