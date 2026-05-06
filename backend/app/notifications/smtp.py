"""SMTP-Versand. Liest die SMTP-Konfiguration aus der DB.

Versand ist absichtlich synchron in einem Background-Task. Wenn SMTP nicht
erreichbar ist, wird der Fehler geloggt — der Workflow-Schritt selbst ist
davon nicht abhaengig (Mail ist Best-Effort).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy.orm import Session

from ..config_service.smtp_settings import SmtpSettings, get_smtp_settings
from ..database import SessionLocal

log = logging.getLogger("notifications")


class NotificationsDisabled(Exception):
    """smtp_config.enabled=False — Versand uebersprungen."""


def send_email(*, to: list[str], subject: str, body: str,
               db: Session | None = None) -> None:
    """Schickt eine Plaintext-Mail. Wirft Exceptions bei SMTP-Problemen.

    Wenn der Aufrufer keine Session uebergibt, oeffnen wir eine eigene —
    so funktioniert die Funktion auch aus FastAPI-BackgroundTasks heraus.
    """
    own_session = db is None
    try:
        if own_session:
            db = SessionLocal()
        s = get_smtp_settings(db)
        _send_with_settings(s, to=to, subject=subject, body=body)
    finally:
        if own_session and db is not None:
            db.close()


def _send_with_settings(s: SmtpSettings, *, to: list[str], subject: str, body: str) -> None:
    if not s.enabled:
        raise NotificationsDisabled()
    if not to:
        log.info("send_email: keine Empfaenger — Versand uebersprungen.")
        return

    msg = EmailMessage()
    msg["From"] = formataddr(("Bank Workflow", s.mail_from))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(
        domain=s.mail_from.split("@")[-1] if "@" in s.mail_from else "bws.local"
    )
    msg.set_content(body, charset="utf-8")

    with smtplib.SMTP(s.host, s.port, timeout=10) as smtp:
        if s.use_tls:
            smtp.starttls()
        if s.username:
            smtp.login(s.username, s.password)
        smtp.send_message(msg)
    log.info("Mail versendet: subject=%r, to=%s", subject, to)
