"""Hohe Ebene: aus einem Workflow-Ereignis E-Mails zusammenstellen und versenden.

Templates und SMTP-Konfiguration kommen aus der DB (siehe config_service).
Die Dispatcher-Funktionen sind so gebaut, dass sie ueber FastAPI BackgroundTasks
aufgerufen werden koennen — sie nehmen einfache Argumente (keine ORM-Objekte
oder DB-Sessions) und oeffnen sich bei Bedarf eine eigene DB-Session.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config_service.role_emails import email_for_user, emails_for_role
from ..config_service.smtp_settings import get_smtp_settings
from ..config_service.templates import render
from ..database import SessionLocal
from .smtp import NotificationsDisabled, send_email

log = logging.getLogger("notifications")


def _antrag_titel(daten: dict) -> str:
    return (
        daten.get("vorhaben", {}).get("titel")
        or daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )


def _antrag_link(app_url: str, instance_id: str) -> str:
    return f"{app_url.rstrip('/')}/antraege/{instance_id}"


def _fmt_datetime(dt: datetime | None) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"


def _open() -> Session:
    return SessionLocal()


def notify_stage_review_pending(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    stage: str,
    rolle: str,
    antragsteller: str,
    erstellt_am: datetime,
) -> None:
    with _open() as db:
        s = get_smtp_settings(db)
        to = emails_for_role(db, rolle)
        if not to:
            log.info("Keine Empfaenger fuer Rolle %r — keine Mail versendet.", rolle)
            return
        mail = render(db, "stage_review_pending", {
            "rolle": rolle,
            "stage": stage,
            "titel": _antrag_titel(daten),
            "schema_version": schema_version,
            "antragsteller": antragsteller,
            "erstellt_am": _fmt_datetime(erstellt_am),
            "link": _antrag_link(s.app_url, instance_id),
        })
        _try_send(db, to, mail.subject, mail.body)


def notify_approved(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    abgeschlossen_am: datetime | None,
) -> None:
    with _open() as db:
        s = get_smtp_settings(db)
        to_addr = email_for_user(db, antragsteller)
        if not to_addr:
            log.info("Antragsteller %r ohne E-Mail — keine Mail versendet.", antragsteller)
            return
        mail = render(db, "approved", {
            "antragsteller": antragsteller,
            "titel": _antrag_titel(daten),
            "schema_version": schema_version,
            "abgeschlossen_am": _fmt_datetime(abgeschlossen_am),
            "link": _antrag_link(s.app_url, instance_id),
        })
        _try_send(db, [to_addr], mail.subject, mail.body)


def notify_rejected(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> None:
    with _open() as db:
        s = get_smtp_settings(db)
        to_addr = email_for_user(db, antragsteller)
        if not to_addr:
            return
        mail = render(db, "rejected", {
            "antragsteller": antragsteller,
            "rolle": rolle,
            "titel": _antrag_titel(daten),
            "schema_version": schema_version,
            "kommentar": kommentar or "— keine Begruendung —",
            "link": _antrag_link(s.app_url, instance_id),
        })
        _try_send(db, [to_addr], mail.subject, mail.body)


def notify_returned(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> None:
    with _open() as db:
        s = get_smtp_settings(db)
        to_addr = email_for_user(db, antragsteller)
        if not to_addr:
            return
        mail = render(db, "returned", {
            "antragsteller": antragsteller,
            "rolle": rolle,
            "titel": _antrag_titel(daten),
            "schema_version": schema_version,
            "kommentar": kommentar or "— kein Hinweis —",
            "link": _antrag_link(s.app_url, instance_id),
        })
        _try_send(db, [to_addr], mail.subject, mail.body)


def _try_send(db: Session, to: list[str], subject: str, body: str) -> None:
    try:
        send_email(to=to, subject=subject, body=body, db=db)
    except NotificationsDisabled:
        log.debug("SMTP deaktiviert — Mail nicht versendet.")
    except Exception as e:  # noqa: BLE001 — Best-Effort, Workflow darf nicht scheitern
        log.warning("Mail-Versand fehlgeschlagen: %s (subject=%r, to=%s)", e, subject, to)
