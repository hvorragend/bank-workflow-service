"""Endpoints for FormInstances (the actual filled-out applications).

Mit Commit 2 sind alle /instances-Endpunkte auth-pflichtig. `genehmiger` und
`rolle` werden aus dem JWT gelesen statt aus dem Request-Body — die Identitaet
ist nicht mehr selbst-deklariert.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, workflow
from ..auth.dependencies import get_current_user
from ..auth.schemas import AuthenticatedUser
from ..database import get_db

router = APIRouter(prefix="/instances", tags=["instances"])


@router.get("", response_model=list[schemas.FormInstanceWithSchema])
def list_instances(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Liste aller Antraege, neueste zuerst."""
    instances = list(
        db.scalars(
            select(models.FormInstance).order_by(models.FormInstance.erstellt_am.desc())
        ).all()
    )
    return [_to_instance_with_schema(i) for i in instances]


def _validate_against_definition(daten: dict, definition: models.FormDefinition) -> None:
    """Validiert Antragsdaten gegen das JSON-Schema der GEPINNTEN Definitionsversion."""
    try:
        Draft202012Validator(definition.json_schema).validate(daten)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Validierungsfehler gegen Schema {definition.typ}/{definition.version}: "
                f"{e.message} (Pfad: {'/'.join(str(p) for p in e.absolute_path)})"
            ),
        )


@router.post("", response_model=schemas.FormInstanceWithSchema, status_code=status.HTTP_201_CREATED)
def create_instance(
    payload: schemas.FormInstanceCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Legt einen neuen Antrag an. Bindet ihn unwiderruflich an die gewaehlte FormDefinition.

    Der `antragsteller` wird aus dem JWT abgeleitet — der Body-Wert (falls
    mitgesendet) wird ignoriert.
    """
    definition = db.get(models.FormDefinition, payload.form_definition_id)
    if not definition:
        raise HTTPException(404, "FormDefinition nicht gefunden.")
    if definition.status != "active":
        raise HTTPException(
            409,
            f"FormDefinition {definition.typ}/{definition.version} ist nicht aktiv "
            f"(Status: {definition.status}). Antraege nur gegen aktive Versionen.",
        )

    _validate_against_definition(payload.daten, definition)

    instance = models.FormInstance(
        form_definition_id=definition.id,
        daten=payload.daten,
        antragsteller=user.username,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


@router.get("/{instance_id}", response_model=schemas.FormInstanceWithSchema)
def get_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Liefert den Antrag plus gepinnte Schemas, fertig zum Rendern im UI."""
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    # Re-validate on read — schuetzt vor Schema-Drift durch direkte DB-Schreibvorgaenge.
    _validate_against_definition(instance.daten, instance.definition)
    return _to_instance_with_schema(instance)


@router.post("/{instance_id}/submit", response_model=schemas.FormInstanceWithSchema)
def submit_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
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
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Genehmigen, ablehnen oder zur Ueberarbeitung zurueckweisen.

    Identitaet (Genehmiger) und Rollen-Set kommen aus dem JWT; die zur aktuellen
    Stage gehoerende Rolle muss eine der Rollen des Users sein.
    """
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    try:
        workflow.decide(
            db, instance,
            genehmiger=user.username,
            user_roles=user.roles,
            entscheidung=action.entscheidung,
            kommentar=action.kommentar,
        )
    except workflow.WorkflowError as e:
        # 403, wenn die Rolle fehlt; 409 fuer alle anderen State-Probleme.
        msg = str(e)
        if "Erforderliche Rolle nicht vorhanden" in msg:
            raise HTTPException(status.HTTP_403_FORBIDDEN, msg)
        raise HTTPException(status.HTTP_409_CONFLICT, msg)
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


def _to_instance_with_schema(instance: models.FormInstance) -> dict:
    """Antwort-Payload, das Antrag + gepinnte Schemas buendelt."""
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
