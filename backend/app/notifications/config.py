"""Notifications-Konfiguration: SMTP-Settings + Rollen-Email-Mapping."""
from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    notifications_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 1025  # MailHog-Standard im Dev-Stack
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False  # MailHog macht kein TLS; produktiv idR True

    mail_from: str = "noreply@bws.local"
    mail_app_url: str = "http://localhost:8080"  # fuer Links in den Mails

    role_emails_path: str = "config/role_emails.toml"


@lru_cache(maxsize=1)
def get_notification_settings() -> NotificationSettings:
    return NotificationSettings()


def reset_notification_settings_cache() -> None:
    get_notification_settings.cache_clear()


def load_role_emails(path: str | Path | None = None) -> dict[str, list[str]]:
    """Mapping Rolle -> Liste von Empfaengern.

    Beispiel `config/role_emails.toml`:

        [role_emails]
        Vorstand     = ["vorstand@vbga.de"]
        Compliance   = ["compliance@vbga.de"]
        Risikomanagement = ["risiko@vbga.de", "risiko-deputy@vbga.de"]

    Wenn die Datei fehlt, gibt der Lookup ein leeres Dict zurueck und der
    Recipients-Resolver faellt auf local_users.json zurueck.
    """
    p = Path(path) if path is not None else Path(get_notification_settings().role_emails_path)
    if not p.exists():
        return {}
    with p.open("rb") as f:
        raw = tomllib.load(f)
    section = raw.get("role_emails", {})
    return {role: list(addrs) for role, addrs in section.items() if isinstance(addrs, list)}
