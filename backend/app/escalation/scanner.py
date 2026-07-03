"""SLA-Scanner: einmal pro Intervall ueber alle aktiven Tasks aller in_pruefung-
Antraege gehen, zwei Stufen pruefen, Mahn-/Eskalations-Mails ausloesen.

Idempotenz: erinnerung_sent_at / eskalation_sent_at pro `FormInstanceActiveStage`-
Row verhindert mehrfachen Versand. Bei Branch-Wechsel entstehen neue Rows mit
leeren _sent_at-Feldern, also auch bei parallelen Branches arbeitet jede Branche
auf ihrer eigenen SLA-Uhr.
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
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

# Prozessweiter Lock um einen kompletten Scan-Durchlauf. Verhindert, dass der
# Admin-getriggerte `run_now` (admin/escalation_router.run_now) und der
# Scheduler-Job gleichzeitig laufen und dieselbe Row doppelt bemailen.
# ACHTUNG: nur prozesslokal — bei mehreren Worker-/Gunicorn-Prozessen oder
# horizontaler Skalierung schuetzt dieser Lock NICHT. Fuer echten Multi-Prozess-
# Betrieb braeuchte es ein DB-Advisory-Lock o. Ae. (bewusst nicht umgesetzt).
_scan_lock = threading.Lock()


# Ergebnis eines Versandversuchs.
_SENT = "sent"        # erfolgreich versendet -> Marker setzen
_SKIPPED = "skipped"  # SMTP deaktiviert -> Marker NICHT setzen, spaeter erneut versuchen
_FAILED = "failed"    # Fehler/kein Empfaenger -> Marker NICHT setzen


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
    return datetime.now(UTC)


def _antrag_titel(daten: dict) -> str:
    return (
        daten.get("vorhaben", {}).get("titel")
        or daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )


def _send_erinnerung(
    db: Session, active: models.FormInstanceActiveStage,
    node: dict[str, Any], age_days: float, sla: int, percent: int = 80,
) -> str:
    smtp = get_smtp_settings(db)
    instance = active.instance
    to = emails_for_role(db, active.rolle)
    if not to:
        log.info("Erinnerung uebersprungen: keine Empfaenger fuer Rolle %r.", active.rolle)
        return _FAILED
    label = node.get("label") or active.node_id
    schwelle_tage = sla * percent / 100
    mail = render(db, "sla_erinnerung", {
        "age_days": f"{age_days:.1f}",
        "stage": label,
        "schwelle_prozent": percent,
        "schwelle_tage": f"{schwelle_tage:.0f}",
        # Backward-Compat fuer bereits angepasste Templates: half_sla traegt jetzt
        # den (konfigurierbaren) Schwellenwert in Tagen.
        "half_sla": f"{schwelle_tage:.0f}",
        "sla": sla,
        "titel": _antrag_titel(instance.daten),
        "antragsteller": instance.antragsteller,
        "link": f"{smtp.app_url.rstrip('/')}/antraege/{instance.id}",
    })
    try:
        send_email(to=to, subject=mail.subject, body=mail.body, db=db)
        return _SENT
    except NotificationsDisabled:
        # SMTP deaktiviert: Marker NICHT setzen, damit beim naechsten Lauf mit
        # aktivem SMTP erneut versucht wird. Der Versand gilt hier NICHT als
        # erledigt (F-018).
        log.info("SMTP deaktiviert — Erinnerung wird spaeter erneut versucht.")
        return _SKIPPED
    except Exception as e:  # noqa: BLE001
        log.warning("Erinnerung konnte nicht versendet werden: %s", e)
        return _FAILED


def _send_eskalation(
    db: Session, active: models.FormInstanceActiveStage,
    node: dict[str, Any], age_days: float, sla: int,
) -> str:
    smtp = get_smtp_settings(db)
    es = get_escalation_settings(db)
    instance = active.instance
    to = emails_for_role(db, es.bereichsleiter_role)
    if not to:
        log.info("Eskalation uebersprungen: keine Empfaenger fuer Rolle %r.", es.bereichsleiter_role)
        return _FAILED
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
        return _SENT
    except NotificationsDisabled:
        # Siehe _send_erinnerung: deaktiviertes SMTP darf nicht als versendet
        # gelten, sonst geht die Eskalation dauerhaft verloren (F-018).
        log.info("SMTP deaktiviert — Eskalation wird spaeter erneut versucht.")
        return _SKIPPED
    except Exception as e:  # noqa: BLE001
        log.warning("Eskalation konnte nicht versendet werden: %s", e)
        return _FAILED


def scan_once(db: Session | None = None) -> dict[str, int]:
    """Eine Iteration des Scanners. Iteriert ueber `FormInstanceActiveStage`-Rows
    aller in_pruefung-Antraege; jede Row hat ihre eigene SLA-Uhr."""
    own_session = db is None
    counts = {"checked": 0, "erinnerungen": 0, "eskalationen": 0, "errors": 0}
    # Ein Scan-Durchlauf ist prozessweit serialisiert (F-017): so kann ein
    # paralleler run_now nicht dieselben Rows ein zweites Mal bemailen.
    with _scan_lock:
        if own_session:
            db = SessionLocal()
        assert db is not None  # ab hier garantiert gesetzt (Typ-Verengung)
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
                        db.commit()
                        continue
                    if stage_start.tzinfo is None:
                        stage_start = stage_start.replace(tzinfo=UTC)
                    age = now - stage_start
                    age_days = age.total_seconds() / 86400.0
                    sla = _sla_days(node, es.default_sla_days)
                    # Stufe 2: SLA ueberschritten und noch nicht eskaliert.
                    if age_days >= sla and not active.eskalation_sent_at:
                        result = _send_eskalation(db, active, node, age_days, sla)
                        if result == _SENT:
                            active.eskalation_sent_at = now
                            audit.write_event(
                                db, kategorie="instance", action="sla.eskalation",
                                akteur=None, target_type="FormInstance", target_id=active.instance_id,
                                payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                         "sla_days": sla, "rolle": active.rolle, "delivery": "sent"},
                                commit=False,
                            )
                            counts["eskalationen"] += 1
                            # F-017: Marker sofort persistieren, bevor die naechste
                            # Row bearbeitet wird — kein Sammel-Commit am Ende.
                            db.commit()
                        elif result == _SKIPPED:
                            # F-018: kein Marker, aber Audit-Spur, dass der Versand
                            # bewusst uebersprungen wurde (SMTP deaktiviert).
                            audit.write_event(
                                db, kategorie="instance", action="sla.eskalation",
                                akteur=None, target_type="FormInstance", target_id=active.instance_id,
                                payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                         "sla_days": sla, "rolle": active.rolle, "delivery": "skipped"},
                                commit=False,
                            )
                            db.commit()
                    # Stufe 1: Vorwarn-Schwelle (Default 80 % der SLA) erreicht und
                    # noch nicht erinnert (N-002, konfigurierbar via reminder_percent).
                    elif (
                        age_days >= sla * es.reminder_percent / 100
                        and not active.erinnerung_sent_at
                        and not active.eskalation_sent_at
                    ):
                        result = _send_erinnerung(db, active, node, age_days, sla, es.reminder_percent)
                        if result == _SENT:
                            active.erinnerung_sent_at = now
                            audit.write_event(
                                db, kategorie="instance", action="sla.erinnerung",
                                akteur=None, target_type="FormInstance", target_id=active.instance_id,
                                payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                         "sla_days": sla, "rolle": active.rolle, "delivery": "sent"},
                                commit=False,
                            )
                            counts["erinnerungen"] += 1
                            db.commit()  # F-017: per-Row-Commit
                        elif result == _SKIPPED:
                            audit.write_event(
                                db, kategorie="instance", action="sla.erinnerung",
                                akteur=None, target_type="FormInstance", target_id=active.instance_id,
                                payload={"node_id": active.node_id, "age_days": round(age_days, 2),
                                         "sla_days": sla, "rolle": active.rolle, "delivery": "skipped"},
                                commit=False,
                            )
                            db.commit()
                except Exception as e:  # noqa: BLE001 — pro Row fail-safe
                    db.rollback()
                    log.exception("SLA-Scan-Fehler fuer active=%s: %s", active.id, e)
                    counts["errors"] += 1
        finally:
            if own_session:
                db.close()
    return counts
