"""DB-gestuetztes Rendern von Notification-Templates.

Variablen-Syntax: $varname (string.Template.safe_substitute) — bewusst kein
Jinja, damit Admin keine Code-Execution einschleusen kann. safe_substitute
laesst unbekannte Variablen einfach als '$varname' stehen, statt zu raisen.
"""
from __future__ import annotations

from string import Template
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..notifications.default_templates import DEFAULT_TEMPLATES


class RenderedEmail(NamedTuple):
    subject: str
    body: str


def get_template(db: Session, key: str) -> tuple[str, str]:
    """Liefert (subject, body) — faellt auf Default zurueck, wenn der Key fehlt."""
    row = db.scalar(select(models.NotificationTemplate).where(models.NotificationTemplate.key == key))
    if row:
        return row.subject, row.body
    if key in DEFAULT_TEMPLATES:
        return DEFAULT_TEMPLATES[key]
    raise KeyError(f"Notification-Template '{key}' nicht gefunden.")


def render(db: Session, key: str, ctx: dict[str, Any]) -> RenderedEmail:
    subject, body = get_template(db, key)
    safe_ctx = {k: ("" if v is None else str(v)) for k, v in ctx.items()}
    return RenderedEmail(
        subject=Template(subject).safe_substitute(safe_ctx),
        body=Template(body).safe_substitute(safe_ctx),
    )


def list_template_keys() -> list[str]:
    """Bekannte Keys aus dem Default-Set — dient dem Admin-UI als Quelle der
    Wahrheit, welche Templates konfigurierbar sind."""
    return list(DEFAULT_TEMPLATES.keys())
