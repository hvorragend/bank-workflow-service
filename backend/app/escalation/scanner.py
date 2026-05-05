"""SLA-Scanner: einmal pro Intervall ueber alle in_pruefung-Antraege gehen,
zwei Stufen pruefen, Mahn-/Eskalations-Mails ausloesen.

Idempotenz: erinnerung_sent_at / eskalation_sent_at auf der Instance verhindern,
dass dieselbe Mahnung mehrfach rausgeht.
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

log = logging.getLogger("escalation")


def _stage_def(instance: models.FormInstance) -> dict[str, Any] | None:
    return next(
        (s for s in instance.definition.workflow_stages if s["name"] == instance.aktuelle_stage),
        None,
    )


def _sla_days(stage: dict[str, Any], default: int) -> int:
    sla = stage.get("sla_days")
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


def _send_erinnerung(db: Session, instance: models.FormInstance, stage: dict[str, Any],
                     age_days: float, sla: int) -> bool:
    smtp = get_smtp_settings(db)
    to = emails_for_role(db, stage["rolle"])
    if not to:
        log.info("Erinnerung uebersprungen: keine Empfaenger fuer Rolle %r.", stage["rolle"])
        return False
    mail = render(db, "sla_erinnerung", {
        "age_days": f"{age_days:.1f}",
        "stage": instance.aktuelle_stage,
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


def _send_eskalation(db: Session, instance: models.FormInstance, stage: dict[str, Any],
                     age_days: float, sla: int) -> bool:
    smtp = get_smtp_settings(db)
    es = get_escalation_settings(db)
    to = emails_for_role(db, es.bereichsleiter_role)
    if not to:
        log.info("Eskalation uebersprungen: keine Empfaenger fuer Rolle %r.", es.bereichsleiter_role)
        return False
    mail = render(db, "sla_eskalation", {
        "age_days": f"{age_days:.1f}",
        "stage": instance.aktuelle_stage,
        "sla": sla,
        "rolle": stage["rolle"],
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
    """Eine Iteration des Scanners. Gibt Counts zurueck."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    counts = {"checked": 0, "erinnerungen": 0, "eskalationen": 0, "errors": 0}
    try:
        es = get_escalation_settings(db)
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
                    inst.stage_eingetreten_am = now
                    continue
                stage_start = inst.stage_eingetreten_am
                if stage_start.tzinfo is None:
                    stage_start = stage_start.replace(tzinfo=timezone.utc)
                age = now - stage_start
                age_days = age.total_seconds() / 86400.0
                sla = _sla_days(stage, es.default_sla_days)
                if age_days >= sla and not inst.eskalation_sent_at:
                    if _send_eskalation(db, inst, stage, age_days, sla):
                        inst.eskalation_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.eskalation",
                            akteur=None, target_type="FormInstance", target_id=inst.id,
                            payload={"stage": inst.aktuelle_stage,
                                     "age_days": round(age_days, 2), "sla_days": sla},
                            commit=False,
                        )
                        counts["eskalationen"] += 1
                elif age_days >= sla / 2 and not inst.erinnerung_sent_at and not inst.eskalation_sent_at:
                    if _send_erinnerung(db, inst, stage, age_days, sla):
                        inst.erinnerung_sent_at = now
                        audit.write_event(
                            db, kategorie="instance", action="sla.erinnerung",
                            akteur=None, target_type="FormInstance", target_id=inst.id,
                            payload={"stage": inst.aktuelle_stage,
                                     "age_days": round(age_days, 2), "sla_days": sla},
                            commit=False,
                        )
                        counts["erinnerungen"] += 1
            except Exception as e:  # noqa: BLE001
                log.exception("SLA-Scan-Fehler fuer %s: %s", inst.id, e)
                counts["errors"] += 1
        db.commit()
    finally:
        if own_session:
            db.close()
    return counts
