"""SLA-Scanner: einmal pro Intervall ueber alle in_pruefung-Antraege gehen,
zwei Stufen pruefen, Mahn-/Eskalations-Mails ausloesen.

Idempotenz: erinnerung_sent_at / eskalation_sent_at auf der Instance verhindern,
dass dieselbe Mahnung mehrfach rausgeht. Beim Stage-Wechsel werden die Felder
zurueckgesetzt (siehe workflow.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models
from ..database import SessionLocal
from ..notifications import dispatcher as notify
from ..notifications import recipients
from ..notifications.config import get_notification_settings
from ..notifications.smtp import NotificationsDisabled, send_email
from .config import get_escalation_settings

log = logging.getLogger("escalation")


def _stage_def(instance: models.FormInstance) -> dict[str, Any] | None:
    return next(
        (s for s in instance.definition.workflow_stages if s["name"] == instance.aktuelle_stage),
        None,
    )


def _sla_days(stage: dict[str, Any]) -> int:
    sla = stage.get("sla_days")
    if isinstance(sla, int) and sla > 0:
        return sla
    return get_escalation_settings().escalation_default_sla_days


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _send_erinnerung(instance: models.FormInstance, stage: dict[str, Any], age_days: float) -> bool:
    """Mahnt die Stage-Rolle. True, wenn Mail tatsaechlich (gemockt) ausgeloest wurde."""
    s = get_notification_settings()
    to = recipients.emails_for_role(stage["rolle"])
    if not to:
        log.info("Erinnerung uebersprungen: keine Empfaenger fuer Rolle %r.", stage["rolle"])
        return False
    titel = (
        instance.daten.get("vorhaben", {}).get("titel")
        or instance.daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )
    sla = _sla_days(stage)
    body = (
        f"Erinnerung: der folgende Antrag wartet seit {age_days:.1f} Tagen "
        f"auf eine Entscheidung in der Stage '{instance.aktuelle_stage}'.\n"
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
        # Notifications komplett aus — wir registrieren die Erinnerung trotzdem
        # im Audit (die SLA-Logik selbst ist davon unabhaengig).
        log.info("NOTIFICATIONS_ENABLED=False — Erinnerung wird trotzdem audit-registriert.")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Erinnerung konnte nicht versendet werden: %s", e)
        return False


def _send_eskalation(instance: models.FormInstance, stage: dict[str, Any], age_days: float) -> bool:
    s = get_notification_settings()
    es = get_escalation_settings()
    to = recipients.emails_for_role(es.escalation_bereichsleiter_role)
    if not to:
        log.info("Eskalation uebersprungen: keine Empfaenger fuer Rolle %r.", es.escalation_bereichsleiter_role)
        return False
    titel = (
        instance.daten.get("vorhaben", {}).get("titel")
        or instance.daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )
    sla = _sla_days(stage)
    body = (
        f"ESKALATION: der folgende Antrag haengt seit {age_days:.1f} Tagen in "
        f"der Stage '{instance.aktuelle_stage}' — das SLA von {sla} Tagen ist "
        f"ueberschritten.\n\n"
        f"Erforderliche Rolle: {stage['rolle']}\n"
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
    """Eine Iteration des Scanners. Gibt Counts zurueck, damit Tests pruefen koennen,
    welche Stufen ausgeloest wurden.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    counts = {"checked": 0, "erinnerungen": 0, "eskalationen": 0, "errors": 0}
    try:
        instances = list(
            db.scalars(
                select(models.FormInstance).where(models.FormInstance.status == "in_pruefung")
            ).all()
        )
        now = _now()
        for inst in instances:
            counts["checked"] += 1
            try:
                stage = _stage_def(inst)
                if not stage:
                    continue
                if not inst.stage_eingetreten_am:
                    # Bestandsantrag aus alter Welt — wir setzen jetzt den Bezugspunkt.
                    inst.stage_eingetreten_am = now
                    continue
                # SQLite speichert naive datetimes — als UTC interpretieren.
                stage_start = inst.stage_eingetreten_am
                if stage_start.tzinfo is None:
                    stage_start = stage_start.replace(tzinfo=timezone.utc)
                age = now - stage_start
                age_days = age.total_seconds() / 86400.0
                sla = _sla_days(stage)
                # Stufe 2: SLA ueberschritten und noch nicht eskaliert.
                if age_days >= sla and not inst.eskalation_sent_at:
                    if _send_eskalation(inst, stage, age_days):
                        inst.eskalation_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.eskalation",
                            akteur=None, target_type="FormInstance", target_id=inst.id,
                            payload={"stage": inst.aktuelle_stage, "age_days": round(age_days, 2),
                                     "sla_days": sla},
                            commit=False,
                        )
                        counts["eskalationen"] += 1
                # Stufe 1: SLA halb verbraucht und noch nicht erinnert.
                elif age_days >= sla / 2 and not inst.erinnerung_sent_at and not inst.eskalation_sent_at:
                    if _send_erinnerung(inst, stage, age_days):
                        inst.erinnerung_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.erinnerung",
                            akteur=None, target_type="FormInstance", target_id=inst.id,
                            payload={"stage": inst.aktuelle_stage, "age_days": round(age_days, 2),
                                     "sla_days": sla},
                            commit=False,
                        )
                        counts["erinnerungen"] += 1
            except Exception as e:  # noqa: BLE001 — pro Antrag fail-safe
                log.exception("SLA-Scan-Fehler fuer %s: %s", inst.id, e)
                counts["errors"] += 1
        db.commit()
    finally:
        if own_session:
            db.close()
    return counts
