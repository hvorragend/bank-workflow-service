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


def decide(
    db: Session,
    instance: models.FormInstance,
    *,
    genehmiger: str,
    rolle: str,
    entscheidung: str,
    kommentar: str | None,
) -> models.Approval:
    """Apply an approval decision. Always writes an audit record, even on rejection."""
    if instance.status != "in_pruefung":
        raise WorkflowError(
            f"Antrag ist nicht in Prüfung (aktuell: {instance.status}). "
            "Genehmigung nicht möglich."
        )

    stages = instance.definition.workflow_stages
    current_idx = next(
        (i for i, s in enumerate(stages) if s["name"] == instance.aktuelle_stage),
        None,
    )
    if current_idx is None:
        raise WorkflowError(f"Unbekannte aktuelle Stage: {instance.aktuelle_stage}.")

    expected_rolle = stages[current_idx]["rolle"]
    if rolle != expected_rolle:
        raise WorkflowError(
            f"Falsche Rolle. Erwartet: '{expected_rolle}', erhalten: '{rolle}'."
        )

    # Audit record is written for every decision — never skipped.
    approval = models.Approval(
        instance_id=instance.id,
        stage=instance.aktuelle_stage,
        genehmiger=genehmiger,
        rolle=rolle,
        entscheidung=entscheidung,
        kommentar=kommentar,
    )
    db.add(approval)

    if entscheidung == "approved":
        if current_idx + 1 < len(stages):
            instance.aktuelle_stage = stages[current_idx + 1]["name"]
        else:
            instance.aktuelle_stage = "abgeschlossen"
            instance.status = "genehmigt"
            instance.abgeschlossen_am = _utcnow()
    elif entscheidung == "rejected":
        instance.status = "abgelehnt"
        instance.abgeschlossen_am = _utcnow()
    elif entscheidung == "returned":
        instance.status = "entwurf"
        instance.aktuelle_stage = "entwurf"
    else:
        raise WorkflowError(f"Unbekannte Entscheidung: {entscheidung}.")

    return approval
