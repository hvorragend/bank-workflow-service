"""SLA-Scanner: einmal pro Intervall ueber alle aktiven Tasks aller in_pruefung-
Antraege gehen, zwei Stufen pruefen, Mahn-/Eskalations-Mails ausloesen.

Idempotenz: erinnerung_sent_at / eskalation_sent_at pro `FormInstanceActiveStage`-
Row verhindert mehrfachen Versand. Bei Branch-Wechsel entstehen neue Rows mit
leeren _sent_at-Feldern, also auch bei parallelen Branches arbeitet jede Branche
auf ihrer eigenen SLA-Uhr.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models
from ..config_service.escalation_settings import get_escalation_settings
from ..config_service.role_emails import emails_for_role
from ..config_service.smtp_settings import get_smtp_settings
from ..config_service.templates import render
from ..database import SessionLocal
from ..notifications.smtp import NotificationsDisabled, send_email
from ..workflow_graph import nodes_by_id

log = logging.getLogger("escalation")


def _node_for_active(active: models.FormInstanceActiveStage) -> dict[str, Any] | None:
    graph = active.instance.definition.workflow_graph
    if not graph:
        return None
    return nodes_by_id(graph).get(active.node_id)


def _sla_days(node: dict[str, Any], default: int) -> int:
    sla = node.get("sla_days")
    if isinstance(sla, int) and sla > 0:
        return sla
    return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _antrag_titel(daten: dict) -> str:
    return (
        daten.get("vorhaben", {}).get("titel")
        or daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )


def _send_erinnerung(
    db: Session, active: models.FormInstanceActiveStage,
    node: dict[str, Any], age_days: float, sla: int,
) -> bool:
    smtp = get_smtp_settings(db)
    instance = active.instance
    to = emails_for_role(db, active.rolle)
    if not to:
        log.info("Erinnerung uebersprungen: keine Empfaenger fuer Rolle %r.", active.rolle)
        return False
    label = node.get("label") or active.node_id
    mail = render(db, "sla_erinnerung", {
        "age_days": f"{age_days:.1f}",
        "stage": label,
        "half_sla": f"{sla / 2:.0f}",
        "sla": sla,
        "titel": _antrag_titel(instance.daten),
        "antragsteller": instance.antragsteller,
        "link": f"{smtp.app_url.rstrip('/')}/antraege/{instance.id}",
    })
    try:
        send_email(to=to, subject=mail.subject, body=mail.body, db=db)
        return True
    except NotificationsDisabled:
        log.info("SMTP deaktiviert — Erinnerung wird trotzdem audit-registriert.")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Erinnerung konnte nicht versendet werden: %s", e)
        return False


def _send_eskalation(
    db: Session, active: models.FormInstanceActiveStage,
    node: dict[str, Any], age_days: float, sla: int,
) -> bool:
    smtp = get_smtp_settings(db)
    es = get_escalation_settings(db)
    instance = active.instance
    to = emails_for_role(db, es.bereichsleiter_role)
    if not to:
        log.info("Eskalation uebersprungen: keine Empfaenger fuer Rolle %r.", es.bereichsleiter_role)
        return False
    label = node.get("label") or active.node_id
    mail = render(db, "sla_eskalation", {
        "age_days": f"{age_days:.1f}",
        "stage": label,
        "sla": sla,
        "rolle": active.rolle,
        "titel": _antrag_titel(instance.daten),
        "antragsteller": instance.antragsteller,
        "link": f"{smtp.app_url.rstrip('/')}/antraege/{instance.id}",
    })
    try:
        send_email(to=to, subject=mail.subject, body=mail.body, db=db)
        return True
    except NotificationsDisabled:
        log.info("SMTP deaktiviert — Eskalation wird trotzdem audit-registriert.")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Eskalation konnte nicht versendet werden: %s", e)
        return False


def scan_once(db: Session | None = None) -> dict[str, int]:
    """Eine Iteration des Scanners. Iteriert ueber `FormInstanceActiveStage`-Rows
    aller in_pruefung-Antraege; jede Row hat ihre eigene SLA-Uhr."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    counts = {"checked": 0, "erinnerungen": 0, "eskalationen": 0, "errors": 0}
    try:
        es = get_escalation_settings(db)
        actives = list(
            db.scalars(
                select(models.FormInstanceActiveStage)
                .join(models.FormInstance, models.FormInstance.id == models.FormInstanceActiveStage.instance_id)
                .where(models.FormInstance.status == "in_pruefung")
            ).all()
        )
        now = _now()
        for active in actives:
            counts["checked"] += 1
            try:
                node = _node_for_active(active)
                if not node:
                    continue
                stage_start = active.eingetreten_am
                if stage_start is None:
                    active.eingetreten_am = now
                    continue
                if stage_start.tzinfo is None:
                    stage_start = stage_start.replace(tzinfo=timezone.utc)
                age = now - stage_start
                age_days = age.total_seconds() / 86400.0
                sla = _sla_days(node, es.default_sla_days)
                # Stufe 2: SLA ueberschritten und noch nicht eskaliert.
                if age_days >= sla and not active.eskalation_sent_at:
                    if _send_eskalation(db, active, node, age_days, sla):
                        active.eskalation_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.eskalation",
                            akteur=None, target_type="FormInstance", target_id=active.instance_id,
                            payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                     "sla_days": sla, "rolle": active.rolle},
                            commit=False,
                        )
                        counts["eskalationen"] += 1
                # Stufe 1: SLA halb verbraucht und noch nicht erinnert.
                elif age_days >= sla / 2 and not active.erinnerung_sent_at and not active.eskalation_sent_at:
                    if _send_erinnerung(db, active, node, age_days, sla):
                        active.erinnerung_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.erinnerung",
                            akteur=None, target_type="FormInstance", target_id=active.instance_id,
                            payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                     "sla_days": sla, "rolle": active.rolle},
                            commit=False,
                        )
                        counts["erinnerungen"] += 1
            except Exception as e:  # noqa: BLE001 — pro Row fail-safe
                log.exception("SLA-Scan-Fehler fuer active=%s: %s", active.id, e)
                counts["errors"] += 1
        db.commit()
    finally:
        if own_session:
            db.close()
    return counts
