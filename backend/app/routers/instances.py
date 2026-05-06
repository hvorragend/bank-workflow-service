"""Endpoints for FormInstances (the actual filled-out applications).

Mit Commit 2 sind alle /instances-Endpunkte auth-pflichtig. `genehmiger` und
`rolle` werden aus dem JWT gelesen statt aus dem Request-Body — die Identitaet
ist nicht mehr selbst-deklariert.

Mit der Umstellung auf einen Workflow-DAG koennen mehrere User-Tasks
gleichzeitig aktiv sein (parallele Branches). Jede Entscheidung adressiert
deshalb explizit die Knoten-ID des betroffenen Tasks.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas, workflow
from ..auth.dependencies import get_current_user
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..notifications import dispatcher as notify
from ..workflow_graph import nodes_by_id

router = APIRouter(prefix="/instances", tags=["instances"])


# Wir lassen Listen-Filter und Stats vor den /-Routen mit Path-Param greifen,
# damit FastAPI die Routen in der richtigen Reihenfolge zuordnet.

@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Kennzahlen fuer das Aktuelles-Dashboard."""
    status_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstance.status, func.count())
            .group_by(models.FormInstance.status)
        ).all()
    )

    # Pro-Stage-Counts (active stages aus der neuen Tabelle).
    stage_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstanceActiveStage.node_id, func.count())
            .group_by(models.FormInstanceActiveStage.node_id)
        ).all()
    )

    # Wartet auf mich: Anzahl aktiver Stages, deren Rolle in user.roles liegt.
    waiting_for_me = db.scalar(
        select(func.count(func.distinct(models.FormInstanceActiveStage.instance_id)))
        .where(models.FormInstanceActiveStage.rolle.in_(user.roles))
    ) or 0 if user.roles else 0

    own = db.scalar(
        select(func.count())
        .select_from(models.FormInstance)
        .where(models.FormInstance.antragsteller == user.username)
    ) or 0

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
    wartet_auf_mich: bool = Query(False, description="Nur Antraege mit aktivem Task in einer Rolle des Users"),
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

    if wartet_auf_mich and user.roles:
        # Subquery: Instance-IDs mit aktivem Task in einer Rolle des Users.
        sub = (
            select(models.FormInstanceActiveStage.instance_id)
            .where(models.FormInstanceActiveStage.rolle.in_(user.roles))
            .distinct()
        )
        stmt = stmt.where(models.FormInstance.id.in_(sub))

    if sort == "created_asc":
        stmt = stmt.order_by(models.FormInstance.erstellt_am.asc())
    elif sort == "updated_desc":
        stmt = stmt.order_by(
            func.coalesce(models.FormInstance.abgeschlossen_am, models.FormInstance.erstellt_am).desc()
        )
    else:
        stmt = stmt.order_by(models.FormInstance.erstellt_am.desc())

    stmt = stmt.limit(limit).offset(offset)
    instances = list(db.scalars(stmt).all())

    if format == "csv":
        return _csv_response(instances)

    return [_to_instance_with_schema(i) for i in instances]


def _csv_response(instances: list[models.FormInstance]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, dialect="excel", delimiter=";")
    w.writerow([
        "id", "schema_typ", "schema_version", "antragsteller", "status",
        "aktive_stages", "erstellt_am", "abgeschlossen_am", "titel",
    ])
    for i in instances:
        titel = (
            (i.daten or {}).get("vorhaben", {}).get("titel")
            or (i.daten or {}).get("beschluss", {}).get("titel")
            or ""
        )
        active_str = ",".join(sorted(a.node_id for a in i.active_stages))
        w.writerow([
            i.id,
            i.definition.typ,
            i.definition.version,
            i.antragsteller,
            i.status,
            active_str,
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
    """Legt einen neuen Antrag an. Bindet ihn unwiderruflich an die gewaehlte FormDefinition."""
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
        activated = workflow.submit(instance)
    except workflow.WorkflowError as e:
        raise HTTPException(409, str(e))
    db.commit()
    db.refresh(instance)

    # Pro initial aktiviertem Task eine Notification — bei direktem Parallel-Split
    # nach dem Start sind das mehrere parallele Mails (das ist gewollt).
    schema_version = f"{instance.definition.typ}/{instance.definition.version}"
    by_id = nodes_by_id(instance.definition.workflow_graph)
    for active in activated:
        node = by_id.get(active.node_id, {})
        background.add_task(
            notify.notify_stage_review_pending,
            instance_id=instance.id,
            daten=instance.daten,
            schema_version=schema_version,
            stage=node.get("label") or active.node_id,
            rolle=active.rolle,
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

    `action.node_id` adressiert den konkreten aktiven User-Task — wichtig, wenn
    parallele Branches gleichzeitig auf eine Entscheidung warten.
    """
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")

    # Rolle vor der Aenderung merken (fuer Reject-/Returned-Mails).
    pre_active = next(
        (a for a in instance.active_stages if a.node_id == action.node_id),
        None,
    )
    pre_rolle = pre_active.rolle if pre_active else "?"

    try:
        _, newly_activated = workflow.decide(
            db, instance,
            node_id=action.node_id,
            genehmiger=user.username,
            user_roles=user.roles,
            entscheidung=action.entscheidung,
            kommentar=action.kommentar,
        )
    except workflow.WorkflowError as e:
        msg = str(e)
        if "Erforderliche Rolle nicht vorhanden" in msg:
            raise HTTPException(status.HTTP_403_FORBIDDEN, msg)
        raise HTTPException(status.HTTP_409_CONFLICT, msg)
    db.commit()
    db.refresh(instance)

    schema_version = f"{instance.definition.typ}/{instance.definition.version}"
    by_id = nodes_by_id(instance.definition.workflow_graph)

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
            for active in newly_activated:
                node = by_id.get(active.node_id, {})
                background.add_task(
                    notify.notify_stage_review_pending,
                    instance_id=instance.id,
                    daten=instance.daten,
                    schema_version=schema_version,
                    stage=node.get("label") or active.node_id,
                    rolle=active.rolle,
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
        "status": instance.status,
        "erstellt_am": instance.erstellt_am,
        "abgeschlossen_am": instance.abgeschlossen_am,
        "approvals": instance.approvals,
        "active_stages": instance.active_stages,
        "json_schema": instance.definition.json_schema,
        "ui_schema": instance.definition.ui_schema,
        "workflow_graph": instance.definition.workflow_graph,
        "schema_version": f"{instance.definition.typ}/{instance.definition.version}",
    }
