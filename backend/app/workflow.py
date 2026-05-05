"""Workflow engine. Drives a FormInstance through the stages defined on its
FormDefinition. Each transition produces an immutable Approval record.

The stages are read from the FormDefinition (not hardcoded), so different
form types can have different approval chains — and a v1 of a form can have
a different chain than v2 of the same form.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models


class WorkflowError(Exception):
    """Raised when an action is invalid for the current state."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def submit(instance: models.FormInstance) -> None:
    """Move an instance from 'entwurf' to the first approval stage."""
    if instance.status != "entwurf":
        raise WorkflowError(f"Antrag ist nicht im Entwurfsstatus (aktuell: {instance.status}).")

    stages = instance.definition.workflow_stages
    if not stages:
        raise WorkflowError("Diese Formulardefinition hat keine Workflow-Stages.")

    instance.aktuelle_stage = stages[0]["name"]
    instance.status = "in_pruefung"
    # SLA-Tracking startet jetzt — Scheduler nutzt das als Bezugspunkt.
    instance.stage_eingetreten_am = _utcnow()
    instance.erinnerung_sent_at = None
    instance.eskalation_sent_at = None


def decide(
    db: Session,
    instance: models.FormInstance,
    *,
    genehmiger: str,
    user_roles: list[str],
    entscheidung: str,
    kommentar: str | None,
) -> models.Approval:
    """Wendet eine Genehmigungs-Entscheidung an. Schreibt immer einen Audit-Eintrag.

    Identitaet und Rollen kommen aus dem JWT — nicht aus dem Request-Body.
    """
    if instance.status != "in_pruefung":
        raise WorkflowError(
            f"Antrag ist nicht in Pruefung (aktuell: {instance.status}). "
            "Genehmigung nicht moeglich."
        )

    stages = instance.definition.workflow_stages
    current_idx = next(
        (i for i, s in enumerate(stages) if s["name"] == instance.aktuelle_stage),
        None,
    )
    if current_idx is None:
        raise WorkflowError(f"Unbekannte aktuelle Stage: {instance.aktuelle_stage}.")

    expected_rolle = stages[current_idx]["rolle"]
    if expected_rolle not in user_roles:
        raise WorkflowError(
            f"Erforderliche Rolle nicht vorhanden. Benoetigt: '{expected_rolle}', "
            f"vorhanden: {sorted(user_roles)}."
        )

    # Audit-Eintrag wird IMMER geschrieben — auch bei Ablehnung. rolle = die zur
    # Stage gehoerende Rolle, die der User aus seinem Rollen-Set erfuellt hat.
    approval = models.Approval(
        instance_id=instance.id,
        stage=instance.aktuelle_stage,
        genehmiger=genehmiger,
        rolle=expected_rolle,
        entscheidung=entscheidung,
        kommentar=kommentar,
    )
    db.add(approval)

    if entscheidung == "approved":
        if current_idx + 1 < len(stages):
            instance.aktuelle_stage = stages[current_idx + 1]["name"]
            # Stage-Wechsel: SLA-Tracking auf neue Stage zuruecksetzen.
            instance.stage_eingetreten_am = _utcnow()
            instance.erinnerung_sent_at = None
            instance.eskalation_sent_at = None
        else:
            instance.aktuelle_stage = "abgeschlossen"
            instance.status = "genehmigt"
            instance.abgeschlossen_am = _utcnow()
            instance.stage_eingetreten_am = None
    elif entscheidung == "rejected":
        instance.status = "abgelehnt"
        instance.abgeschlossen_am = _utcnow()
        instance.stage_eingetreten_am = None
    elif entscheidung == "returned":
        instance.status = "entwurf"
        instance.aktuelle_stage = "entwurf"
        instance.stage_eingetreten_am = None
        instance.erinnerung_sent_at = None
        instance.eskalation_sent_at = None
    else:
        raise WorkflowError(f"Unbekannte Entscheidung: {entscheidung}.")

    return approval
