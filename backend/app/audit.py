"""Schreib-Helper fuer Audit-Eintraege.

Schreibt parallel in Container-Log (strukturiert via stdlib logging) und in die
audit_events-Tabelle, damit Admin-UI und Container-Sammler unabhaengig sind.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from . import models

log = logging.getLogger("audit")


def write_event(
    db: Session,
    *,
    kategorie: str,
    action: str,
    akteur: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> models.AuditEvent:
    """Persistiert einen Audit-Eintrag und logt parallel in stdout."""
    ev = models.AuditEvent(
        kategorie=kategorie,
        action=action,
        akteur=akteur,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        payload=payload,
    )
    db.add(ev)
    if commit:
        db.commit()
    log.info(
        "audit.%s.%s",
        kategorie,
        action,
        extra={
            "audit_kategorie": kategorie,
            "audit_action": action,
            "audit_akteur": akteur,
            "audit_target": f"{target_type}:{target_id}" if target_type else None,
            "audit_ip": ip,
        },
    )
    return ev
