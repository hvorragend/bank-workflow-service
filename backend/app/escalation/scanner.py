"""SLA-Scanner: einmal pro Intervall ueber alle aktiven Tasks aller in_pruefung-
Antraege gehen, zwei Stufen pruefen, Mahn-/Eskalations-Mails ausloesen.

Idempotenz: erinnerung_sent_at / eskalation_sent_at pro `FormInstanceActiveStage`-
Row verhindert mehrfachen Versand. Bei Branch-Wechsel entstehen neue Rows mit
leeren _sent_at-Feldern, also auch bei parallelen Branches arbeitet jede Branche
auf ihrer eigenen SLA-Uhr.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models
from ..database import SessionLocal
from ..notifications import recipients
from ..notifications.config import get_notification_settings
from ..notifications.smtp import NotificationsDisabled, send_email
from ..workflow_graph import nodes_by_id
from .config import get_escalation_settings

log = logging.getLogger("escalation")


def _node_for_active(active: models.FormInstanceActiveStage) -> dict[str, Any] | None:
    graph = active.instance.definition.workflow_graph
    if not graph:
        return None
    return nodes_by_id(graph).get(active.node_id)


def _sla_days(node: dict[str, Any]) -> int:
    sla = node.get("sla_days")
    if isinstance(sla, int) and sla > 0:
        return sla
    return get_escalation_settings().escalation_default_sla_days


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _send_erinnerung(active: models.FormInstanceActiveStage, node: dict[str, Any], age_days: float) -> bool:
    s = get_notification_settings()
    instance = active.instance
    to = recipients.emails_for_role(active.rolle)
    if not to:
        log.info("Erinnerung uebersprungen: keine Empfaenger fuer Rolle %r.", active.rolle)
        return False
    titel = (
        instance.daten.get("vorhaben", {}).get("titel")
        or instance.daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )
    sla = _sla_days(node)
    label = node.get("label") or active.node_id
    body = (
        f"Erinnerung: der folgende Antrag wartet seit {age_days:.1f} Tagen "
        f"auf eine Entscheidung in der Stage '{label}'.\n"
        f"Das halbe SLA ({sla / 2:.0f} Tage) ist erreicht.\n\n"
        f"Titel:        {titel}\n"
        f"Antragsteller: {instance.antragsteller}\n"
        f"Direktlink:    {s.mail_app_url.rstrip('/')}/antraege/{instance.id}\n\n"
        f"Bitte zeitnah pruefen — bei {sla} Tagen ohne Entscheidung wird an "
        f"den Bereichsleiter eskaliert."
    )
    try:
        send_email(to=to, subject=f"[Bank Workflow] Erinnerung — wartet seit {age_days:.1f} Tagen", body=body)
        return True
    except NotificationsDisabled:
        log.info("NOTIFICATIONS_ENABLED=False — Erinnerung wird trotzdem audit-registriert.")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Erinnerung konnte nicht versendet werden: %s", e)
        return False


def _send_eskalation(active: models.FormInstanceActiveStage, node: dict[str, Any], age_days: float) -> bool:
    s = get_notification_settings()
    es = get_escalation_settings()
    instance = active.instance
    to = recipients.emails_for_role(es.escalation_bereichsleiter_role)
    if not to:
        log.info("Eskalation uebersprungen: keine Empfaenger fuer Rolle %r.", es.escalation_bereichsleiter_role)
        return False
    titel = (
        instance.daten.get("vorhaben", {}).get("titel")
        or instance.daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )
    sla = _sla_days(node)
    label = node.get("label") or active.node_id
    body = (
        f"ESKALATION: der folgende Antrag haengt seit {age_days:.1f} Tagen in "
        f"der Stage '{label}' — das SLA von {sla} Tagen ist ueberschritten.\n\n"
        f"Erforderliche Rolle: {active.rolle}\n"
        f"Titel:               {titel}\n"
        f"Antragsteller:       {instance.antragsteller}\n"
        f"Direktlink:          {s.mail_app_url.rstrip('/')}/antraege/{instance.id}\n\n"
        f"Bitte greifen Sie ein — entweder direkt entscheiden, falls die Rolle "
        f"das zulaesst, oder die zustaendige Person aktiv ansprechen."
    )
    try:
        send_email(to=to, subject=f"[Bank Workflow] ESKALATION — SLA ueberschritten", body=body)
        return True
    except NotificationsDisabled:
        log.info("NOTIFICATIONS_ENABLED=False — Eskalation wird trotzdem audit-registriert.")
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
                sla = _sla_days(node)
                # Stufe 2: SLA ueberschritten und noch nicht eskaliert.
                if age_days >= sla and not active.eskalation_sent_at:
                    if _send_eskalation(active, node, age_days):
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
                    if _send_erinnerung(active, node, age_days):
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
