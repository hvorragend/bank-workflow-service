"""Endpoints for FormInstances (the actual filled-out applications).

Mit Commit 2 sind alle /instances-Endpunkte auth-pflichtig. `genehmiger` und
`rolle` werden aus dem JWT gelesen statt aus dem Request-Body — die Identitaet
ist nicht mehr selbst-deklariert.

Mit Commit 4 (Dashboard + Archiv) bekommt /instances Filter-Parameter und
einen /stats-Endpoint fuer Kennzahlen.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .. import models, schemas, workflow
from ..auth.dependencies import get_current_user
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..notifications import dispatcher as notify

router = APIRouter(prefix="/instances", tags=["instances"])


# Wir lassen Listen-Filter und Stats vor den /-Routen mit Path-Param greifen,
# damit FastAPI die Routen in der richtigen Reihenfolge zuordnet.

@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Kennzahlen fuer das Aktuelles-Dashboard.

    - Counts pro Status, pro Stage
    - Wartet auf den eingeloggten User (Stage-Rolle in user.roles)
    - Eigene Antraege (antragsteller == user.username)
    - Letzte 7 Tage: erstellt / abgeschlossen
    - Durchschnittliche Bearbeitungsdauer in Tagen (genehmigte Antraege)
    """
    # Pro-Status-Counts
    status_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstance.status, func.count())
            .group_by(models.FormInstance.status)
        ).all()
    )

    # Pro-Stage-Counts (nur in_pruefung)
    stage_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstance.aktuelle_stage, func.count())
            .where(models.FormInstance.status == "in_pruefung")
            .group_by(models.FormInstance.aktuelle_stage)
        ).all()
    )

    # Wartet auf mich: alle in_pruefung-Antraege, deren Stage-Rolle in user.roles ist.
    # Das machen wir in Python, weil workflow_stages JSON in SQLite ist und ein
    # SQL-seitiger Filter nicht portabel waere.
    pending = list(
        db.scalars(
            select(models.FormInstance).where(models.FormInstance.status == "in_pruefung")
        ).all()
    )
    waiting_for_me = 0
    for inst in pending:
        stages = inst.definition.workflow_stages
        match = next((s for s in stages if s["name"] == inst.aktuelle_stage), None)
        if match and match.get("rolle") in user.roles:
            waiting_for_me += 1

    # Eigene Antraege
    own = db.scalar(
        select(func.count())
        .select_from(models.FormInstance)
        .where(models.FormInstance.antragsteller == user.username)
    ) or 0

    # Letzte 7 Tage
    now = datetime.now(timezone.utc)
    cutoff = now - _timedelta_days(7)
    last7_created = db.scalar(
        select(func.count())
        .select_from(models.FormInstance)
        .where(models.FormInstance.erstellt_am >= cutoff)
    ) or 0
    last7_decided = db.scalar(
        select(func.count())
        .select_from(models.FormInstance)
        .where(models.FormInstance.abgeschlossen_am >= cutoff)
    ) or 0

    # Durchschnittsdauer (genehmigte Antraege) — in Python, weil JULIANDAY/EXTRACT
    # zwischen SQLite und Postgres unterschiedlich heisst.
    decided = list(
        db.scalars(
            select(models.FormInstance).where(models.FormInstance.status == "genehmigt")
        ).all()
    )
    durations_days = [
        (i.abgeschlossen_am - i.erstellt_am).total_seconds() / 86400
        for i in decided
        if i.abgeschlossen_am and i.erstellt_am
    ]
    avg_days = round(sum(durations_days) / len(durations_days), 1) if durations_days else None

    return {
        "status_counts": status_counts,
        "stage_counts": stage_counts,
        "waiting_for_me": waiting_for_me,
        "own_instances": own,
        "last7_created": last7_created,
        "last7_decided": last7_decided,
        "avg_decision_days": avg_days,
    }


def _timedelta_days(days: int):
    from datetime import timedelta
    return timedelta(days=days)


@router.get("")
def list_instances(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
    mein: bool = Query(False, description="Nur Antraege des eingeloggten Antragstellers"),
    wartet_auf_mich: bool = Query(False, description="Nur Antraege, deren aktuelle Stage zu meinen Rollen passt"),
    status_in: list[str] | None = Query(None, alias="status", description="Status-Filter (Mehrfach erlaubt)"),
    typ: str | None = Query(None, description="Filter auf FormDefinition.typ"),
    version: str | None = Query(None, description="Filter auf FormDefinition.version"),
    created_from: datetime | None = Query(None, description="Erstellt ab (ISO-8601)"),
    created_to:   datetime | None = Query(None, description="Erstellt bis (ISO-8601)"),
    sort: Literal["created_desc", "created_asc", "updated_desc"] = Query("created_desc"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    format: Literal["json", "csv"] = Query("json"),
):
    """Liste der Antraege. Filterung serverseitig — verhindert das Nachladen
    der gesamten Tabelle ins Frontend, sobald das Archiv waechst."""
    stmt = select(models.FormInstance)

    if mein:
        stmt = stmt.where(models.FormInstance.antragsteller == user.username)

    if status_in:
        stmt = stmt.where(models.FormInstance.status.in_(status_in))

    if created_from:
        stmt = stmt.where(models.FormInstance.erstellt_am >= created_from)
    if created_to:
        stmt = stmt.where(models.FormInstance.erstellt_am <= created_to)

    if typ or version:
        stmt = stmt.join(models.FormDefinition,
                         models.FormDefinition.id == models.FormInstance.form_definition_id)
        if typ:
            stmt = stmt.where(models.FormDefinition.typ == typ)
        if version:
            stmt = stmt.where(models.FormDefinition.version == version)

    if sort == "created_asc":
        stmt = stmt.order_by(models.FormInstance.erstellt_am.asc())
    elif sort == "updated_desc":
        # Naeherung: abgeschlossen_am, sonst erstellt_am
        stmt = stmt.order_by(
            func.coalesce(models.FormInstance.abgeschlossen_am, models.FormInstance.erstellt_am).desc()
        )
    else:
        stmt = stmt.order_by(models.FormInstance.erstellt_am.desc())

    stmt = stmt.limit(limit).offset(offset)
    instances = list(db.scalars(stmt).all())

    # "wartet auf mich" — Filter in Python, da Stage-Rollen in workflow_stages JSON liegen.
    if wartet_auf_mich:
        filtered = []
        for inst in instances:
            if inst.status != "in_pruefung":
                continue
            stages = inst.definition.workflow_stages
            match = next((s for s in stages if s["name"] == inst.aktuelle_stage), None)
            if match and match.get("rolle") in user.roles:
                filtered.append(inst)
        instances = filtered

    if format == "csv":
        return _csv_response(instances)

    return [_to_instance_with_schema(i) for i in instances]


def _csv_response(instances: list[models.FormInstance]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, dialect="excel", delimiter=";")
    w.writerow([
        "id", "schema_typ", "schema_version", "antragsteller", "status",
        "aktuelle_stage", "erstellt_am", "abgeschlossen_am", "titel",
    ])
    for i in instances:
        titel = (
            (i.daten or {}).get("vorhaben", {}).get("titel")
            or (i.daten or {}).get("beschluss", {}).get("titel")
            or ""
        )
        w.writerow([
            i.id,
            i.definition.typ,
            i.definition.version,
            i.antragsteller,
            i.status,
            i.aktuelle_stage,
            i.erstellt_am.isoformat() if i.erstellt_am else "",
            i.abgeschlossen_am.isoformat() if i.abgeschlossen_am else "",
            titel,
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="antraege.csv"'},
    )


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
    background: BackgroundTasks,
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

    # Empfaenger-Rolle der ersten Stage informieren — Versand im Hintergrund.
    stage_def = next(
        (s for s in instance.definition.workflow_stages if s["name"] == instance.aktuelle_stage),
        None,
    )
    if stage_def:
        background.add_task(
            notify.notify_stage_review_pending,
            instance_id=instance.id,
            daten=instance.daten,
            schema_version=f"{instance.definition.typ}/{instance.definition.version}",
            stage=instance.aktuelle_stage,
            rolle=stage_def["rolle"],
            antragsteller=instance.antragsteller,
            erstellt_am=instance.erstellt_am,
        )
    return _to_instance_with_schema(instance)


@router.post("/{instance_id}/decide", response_model=schemas.FormInstanceWithSchema)
def decide_instance(
    instance_id: str,
    action: schemas.ApprovalAction,
    background: BackgroundTasks,
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
    # Stage-Rolle vor der Aenderung merken — fuer Reject/Returned-Mails.
    pre_stage_def = next(
        (s for s in instance.definition.workflow_stages if s["name"] == instance.aktuelle_stage),
        None,
    )
    pre_rolle = pre_stage_def["rolle"] if pre_stage_def else "?"

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

    schema_version = f"{instance.definition.typ}/{instance.definition.version}"

    # Notifications je nach neuem Status (Background — Workflow ist bereits committed).
    if action.entscheidung == "approved":
        if instance.status == "genehmigt":
            background.add_task(
                notify.notify_approved,
                instance_id=instance.id,
                daten=instance.daten,
                schema_version=schema_version,
                antragsteller=instance.antragsteller,
                abgeschlossen_am=instance.abgeschlossen_am,
            )
        else:
            # Naechste Stage: deren Rolle informieren
            next_stage = next(
                (s for s in instance.definition.workflow_stages if s["name"] == instance.aktuelle_stage),
                None,
            )
            if next_stage:
                background.add_task(
                    notify.notify_stage_review_pending,
                    instance_id=instance.id,
                    daten=instance.daten,
                    schema_version=schema_version,
                    stage=instance.aktuelle_stage,
                    rolle=next_stage["rolle"],
                    antragsteller=instance.antragsteller,
                    erstellt_am=instance.erstellt_am,
                )
    elif action.entscheidung == "rejected":
        background.add_task(
            notify.notify_rejected,
            instance_id=instance.id,
            daten=instance.daten,
            schema_version=schema_version,
            antragsteller=instance.antragsteller,
            rolle=pre_rolle,
            kommentar=action.kommentar,
        )
    elif action.entscheidung == "returned":
        background.add_task(
            notify.notify_returned,
            instance_id=instance.id,
            daten=instance.daten,
            schema_version=schema_version,
            antragsteller=instance.antragsteller,
            rolle=pre_rolle,
            kommentar=action.kommentar,
        )

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
