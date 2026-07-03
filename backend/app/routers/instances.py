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
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import audit, models, schemas, workflow
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..notifications import dispatcher as notify
from ..workflow_graph import nodes_by_id

router = APIRouter(prefix="/instances", tags=["instances"])

# Permission, die vollen Lesezugriff auf ALLE Antraege gibt (Aufsicht/Revision).
# Wer sie nicht hat, sieht nur eigene oder Antraege, an deren Workflow eine seiner
# Rollen aktuell oder historisch beteiligt ist (Need-to-know).
_READ_ALL_PERM = "instances.reporting"


def _can_read_all(user: AuthenticatedUser) -> bool:
    return _READ_ALL_PERM in user.permissions


def _visibility_filter(user: AuthenticatedUser):
    """SQLAlchemy-Bedingung: Antragsteller ODER beteiligte Rolle (aktiv/historisch)."""
    conds = [models.FormInstance.antragsteller == user.username]
    if user.roles:
        active_sub = (
            select(models.FormInstanceActiveStage.instance_id)
            .where(models.FormInstanceActiveStage.rolle.in_(user.roles))
        )
        approval_sub = (
            select(models.Approval.instance_id)
            .where(models.Approval.rolle.in_(user.roles))
        )
        conds.append(models.FormInstance.id.in_(active_sub))
        conds.append(models.FormInstance.id.in_(approval_sub))
    return or_(*conds)


def _assert_can_view(user: AuthenticatedUser, instance: models.FormInstance) -> None:
    """Harte Sichtbarkeitspruefung fuer Einzelabruf/Anhaenge — verhindert IDOR."""
    if _can_read_all(user):
        return
    if instance.antragsteller == user.username:
        return
    roles = set(user.roles)
    if roles and (
        any(a.rolle in roles for a in instance.active_stages)
        or any(ap.rolle in roles for ap in instance.approvals)
    ):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Kein Zugriff auf diesen Antrag (weder Antragsteller noch beteiligte Rolle).",
    )


def _csv_cell(value) -> str:
    """Neutralisiert fuehrende Formelzeichen (=,+,-,@) gegen CSV-Formel-Injection
    in Excel/LibreOffice, ohne den Wert sonst zu veraendern."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# Wir lassen Listen-Filter und Stats vor den /-Routen mit Path-Param greifen,
# damit FastAPI die Routen in der richtigen Reihenfolge zuordnet.

@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
) -> dict:
    """Kennzahlen fuer das Aktuelles-Dashboard."""
    status_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstance.status, func.count())
            .group_by(models.FormInstance.status)
        ).tuples().all()
    )

    # Pro-Stage-Counts (active stages aus der neuen Tabelle).
    stage_counts: dict[str, int] = dict(
        db.execute(
            select(models.FormInstanceActiveStage.node_id, func.count())
            .group_by(models.FormInstanceActiveStage.node_id)
        ).tuples().all()
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

    now = datetime.now(UTC)
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

    # Durchschnittliche Bearbeitungsdauer als SQL-Aggregat — laedt nicht mehr
    # alle genehmigten Instanzen inkl. daten-Blob in den Speicher (O-004).
    avg_raw = db.scalar(
        select(func.avg(
            func.julianday(models.FormInstance.abgeschlossen_am)
            - func.julianday(models.FormInstance.erstellt_am)
        ))
        .where(models.FormInstance.status == "genehmigt")
        .where(models.FormInstance.abgeschlossen_am.is_not(None))
        .where(models.FormInstance.erstellt_am.is_not(None))
    )
    avg_days = round(avg_raw, 1) if avg_raw is not None else None

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


@router.get("/aging")
def aging(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("instances.read")),
) -> list[dict]:
    """N-005: Aging-Report — je Rolle die Anzahl offener Tasks und der aelteste
    Eintritt. Zeigt, wo sich Genehmigungen stauen (aeltester zuerst)."""
    rows = db.execute(
        select(
            models.FormInstanceActiveStage.rolle,
            func.count(),
            func.min(models.FormInstanceActiveStage.eingetreten_am),
        )
        .join(models.FormInstance,
              models.FormInstance.id == models.FormInstanceActiveStage.instance_id)
        .where(models.FormInstance.status == "in_pruefung")
        .group_by(models.FormInstanceActiveStage.rolle)
    ).all()

    now = datetime.now(UTC)
    result: list[dict] = []
    for rolle, count, oldest in rows:
        alter_tage = None
        if oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            alter_tage = round((now - oldest).total_seconds() / 86400, 1)
        result.append({
            "rolle": rolle,
            "offene_tasks": count,
            "aeltester_eintritt": oldest,
            "alter_tage": alter_tage,
        })
    result.sort(key=lambda r: r["alter_tage"] or 0, reverse=True)
    return result


@router.get("")
def list_instances(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
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

    # Objekt-Level-Sichtbarkeit: Wer keine Reporting-Permission hat, sieht nur
    # eigene oder Antraege mit einer seiner Rollen im Workflow (verhindert IDOR).
    if not _can_read_all(user):
        stmt = stmt.where(_visibility_filter(user))

    # Eager-Load der Relationen, die _to_instance_with_schema/_csv_response
    # ohnehin je Zeile lesen — vermeidet N+1 (O-003).
    stmt = stmt.options(
        selectinload(models.FormInstance.active_stages),
        selectinload(models.FormInstance.approvals),
    )

    if sort == "created_asc":
        stmt = stmt.order_by(models.FormInstance.erstellt_am.asc())
    elif sort == "updated_desc":
        stmt = stmt.order_by(
            func.coalesce(models.FormInstance.abgeschlossen_am, models.FormInstance.erstellt_am).desc()
        )
    else:
        stmt = stmt.order_by(models.FormInstance.erstellt_am.desc())

    # CSV ist ein Export (Revision/Archiv) und darf nicht still bei `limit`
    # abgeschnitten werden (O-005) — Pagination gilt nur fuer die JSON-Liste.
    if format == "csv":
        instances = list(db.scalars(stmt).all())
        return _csv_response(instances)

    stmt = stmt.limit(limit).offset(offset)
    instances = list(db.scalars(stmt).all())
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
        w.writerow([_csv_cell(v) for v in (
            i.id,
            i.definition.typ,
            i.definition.version,
            i.antragsteller,
            i.status,
            active_str,
            i.erstellt_am.isoformat() if i.erstellt_am else "",
            i.abgeschlossen_am.isoformat() if i.abgeschlossen_am else "",
            titel,
        )])
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
        ) from e


@router.post("", response_model=schemas.FormInstanceWithSchema, status_code=status.HTTP_201_CREATED)
def create_instance(
    payload: schemas.FormInstanceCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.create")),
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
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
):
    """Liefert den Antrag plus gepinnte Schemas, fertig zum Rendern im UI."""
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    _assert_can_view(user, instance)
    # Bewusst KEINE Re-Validierung der gespeicherten Daten beim Lesen (F-010):
    # ein Read darf nie an Validierung scheitern, sonst wird ein Altantrag, dessen
    # Daten nicht mehr zum gepinnten Schema passen, per API unlesbar (inkl. Audit).
    return _to_instance_with_schema(instance)


@router.patch("/{instance_id}", response_model=schemas.FormInstanceWithSchema)
def update_instance(
    instance_id: str,
    payload: schemas.FormInstanceUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.create")),
):
    """Bearbeitet die Antragsdaten eines Entwurfs.

    Nur im Status 'entwurf' und nur durch den Antragsteller — macht den
    „Zurueckweisen zur Ueberarbeitung"-Flow ueberhaupt erst umsetzbar (F-016).
    Die Daten werden gegen das gepinnte Schema validiert und die Aenderung
    revisionssicher auditiert.
    """
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    if instance.antragsteller != user.username:
        raise HTTPException(403, "Nur der Antragsteller darf den Entwurf bearbeiten.")
    if instance.status != "entwurf":
        raise HTTPException(
            409,
            f"Antrag ist nicht im Entwurf (Status: {instance.status}). "
            "Nur Entwuerfe sind bearbeitbar.",
        )
    _validate_against_definition(payload.daten, instance.definition)
    instance.daten = payload.daten
    audit.write_event(
        db,
        kategorie="instance",
        action="instance.updated",
        akteur=user.username,
        target_type="FormInstance",
        target_id=instance.id,
        commit=False,
    )
    db.commit()
    db.refresh(instance)
    return _to_instance_with_schema(instance)


@router.post("/{instance_id}/submit", response_model=schemas.FormInstanceWithSchema)
def submit_instance(
    instance_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.create")),
):
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    if instance.antragsteller != user.username:
        raise HTTPException(403, "Nur der Antragsteller darf diesen Antrag einreichen.")
    try:
        activated = workflow.submit(instance)
    except workflow.WorkflowError as e:
        raise HTTPException(409, str(e)) from e
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
    user: AuthenticatedUser = Depends(require_permission("instances.decide", "instances.return")),
):
    """Genehmigen, ablehnen oder zur Ueberarbeitung zurueckweisen.

    `action.node_id` adressiert den konkreten aktiven User-Task — wichtig, wenn
    parallele Branches gleichzeitig auf eine Entscheidung warten.
    """
    # Konkurrierende Entscheidungen auf demselben Antrag serialisieren (F-003).
    # Innerhalb des Locks die Session-Sicht verwerfen, damit unter dem Lock frisch
    # gelesen wird und der zweite Genehmiger die Approval des ersten sieht.
    with workflow.instance_lock(instance_id):
        db.expire_all()
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
                raise HTTPException(status.HTTP_403_FORBIDDEN, msg) from e
            if "Begruendung (Kommentar) erforderlich" in msg:
                raise HTTPException(422, msg) from e
            raise HTTPException(status.HTTP_409_CONFLICT, msg) from e
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
        "lauf": instance.lauf,
        "erstellt_am": instance.erstellt_am,
        "abgeschlossen_am": instance.abgeschlossen_am,
        "approvals": instance.approvals,
        "active_stages": instance.active_stages,
        "json_schema": instance.definition.json_schema,
        "ui_schema": instance.definition.ui_schema,
        "workflow_graph": instance.definition.workflow_graph,
        "schema_version": f"{instance.definition.typ}/{instance.definition.version}",
    }
