"""DB-gestuetzte SMTP-Konfiguration. Loest die Env-Var-basierte
NotificationSettings aus notifications/config.py ab.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models
from ..security import secrets


@dataclass
class SmtpSettings:
    enabled: bool = False
    host: str = "localhost"
    port: int = 1025
    use_tls: bool = False
    username: str = ""
    password: str = ""  # Klartext (entschluesselt)
    mail_from: str = "noreply@bws.local"
    app_url: str = "http://localhost:8080"


def get_smtp_settings(db: Session) -> SmtpSettings:
    cfg = db.get(models.SmtpConfig, 1)
    if cfg is None:
        return SmtpSettings()
    return SmtpSettings(
        enabled=cfg.enabled,
        host=cfg.host,
        port=cfg.port,
        use_tls=cfg.use_tls,
        username=cfg.username,
        password=secrets.decrypt(cfg.password_enc) or "",
        mail_from=cfg.mail_from,
        app_url=cfg.app_url,
    )
