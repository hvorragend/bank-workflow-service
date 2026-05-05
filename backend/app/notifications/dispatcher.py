"""Hohe Ebene: aus einem Workflow-Ereignis E-Mails zusammenstellen und versenden.

Die Funktionen hier sind so gebaut, dass sie ueber FastAPI BackgroundTasks
aufgerufen werden koennen — sie nehmen einfache Argumente (keine ORM-Objekte
oder DB-Sessions) und sind vom Request-Lifecycle entkoppelt.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from . import recipients, templates
from .config import get_notification_settings
from .smtp import NotificationsDisabled, send_email

log = logging.getLogger("notifications")


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
    s = get_notification_settings()
    to = recipients.emails_for_role(rolle)
    if not to:
        log.info("Keine Empfaenger fuer Rolle %r — keine Mail versendet.", rolle)
        return
    mail = templates.template_stage_review_pending(
        app_url=s.mail_app_url,
        instance_id=instance_id,
        daten=daten,
        schema_version=schema_version,
        stage=stage,
        rolle=rolle,
        antragsteller=antragsteller,
        erstellt_am=erstellt_am,
    )
    _try_send(to, mail["subject"], mail["body"])


def notify_approved(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    abgeschlossen_am: datetime | None,
) -> None:
    s = get_notification_settings()
    to_addr = recipients.email_for_user(antragsteller)
    if not to_addr:
        log.info("Antragsteller %r ohne E-Mail — keine Mail versendet.", antragsteller)
        return
    mail = templates.template_approved(
        app_url=s.mail_app_url,
        instance_id=instance_id,
        daten=daten,
        schema_version=schema_version,
        antragsteller=antragsteller,
        abgeschlossen_am=abgeschlossen_am,
    )
    _try_send([to_addr], mail["subject"], mail["body"])


def notify_rejected(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> None:
    s = get_notification_settings()
    to_addr = recipients.email_for_user(antragsteller)
    if not to_addr:
        return
    mail = templates.template_rejected(
        app_url=s.mail_app_url,
        instance_id=instance_id,
        daten=daten,
        schema_version=schema_version,
        antragsteller=antragsteller,
        rolle=rolle,
        kommentar=kommentar,
    )
    _try_send([to_addr], mail["subject"], mail["body"])


def notify_returned(
    *,
    instance_id: str,
    daten: dict[str, Any],
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> None:
    s = get_notification_settings()
    to_addr = recipients.email_for_user(antragsteller)
    if not to_addr:
        return
    mail = templates.template_returned(
        app_url=s.mail_app_url,
        instance_id=instance_id,
        daten=daten,
        schema_version=schema_version,
        antragsteller=antragsteller,
        rolle=rolle,
        kommentar=kommentar,
    )
    _try_send([to_addr], mail["subject"], mail["body"])


def _try_send(to: list[str], subject: str, body: str) -> None:
    try:
        send_email(to=to, subject=subject, body=body)
    except NotificationsDisabled:
        log.debug("Notifications abgeschaltet — Mail nicht versendet.")
    except Exception as e:  # noqa: BLE001 — Best-Effort, Workflow darf nicht scheitern
        log.warning("Mail-Versand fehlgeschlagen: %s (subject=%r, to=%s)", e, subject, to)
