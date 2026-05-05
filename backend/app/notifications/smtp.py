"""SMTP-Versand. Kapselt smtplib + Settings.

Versand ist absichtlich synchron in einem Background-Task. Wenn SMTP nicht
erreichbar ist, wird der Fehler geloggt und ein Audit-Eintrag geschrieben —
der Workflow-Schritt selbst ist davon nicht abhaengig (Mail ist Best-Effort).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .config import get_notification_settings

log = logging.getLogger("notifications")


class NotificationsDisabled(Exception):
    """NOTIFICATIONS_ENABLED ist False — Versand uebersprungen."""


def send_email(*, to: list[str], subject: str, body: str) -> None:
    """Schickt eine Plaintext-Mail. Wirft Exceptions bei SMTP-Problemen.

    Wenn NOTIFICATIONS_ENABLED nicht gesetzt ist, gibt es einen No-op
    (NotificationsDisabled raise — Aufrufer fangen das stumm ab).
    """
    s = get_notification_settings()
    if not s.notifications_enabled:
        raise NotificationsDisabled()
    if not to:
        log.info("send_email: keine Empfaenger — Versand uebersprungen.")
        return

    msg = EmailMessage()
    msg["From"] = formataddr(("Bank Workflow", s.mail_from))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=s.mail_from.split("@")[-1] if "@" in s.mail_from else "bws.local")
    msg.set_content(body, charset="utf-8")

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
    log.info("Mail versendet: subject=%r, to=%s", subject, to)
