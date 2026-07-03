"""DB-gestuetzte Eskalations-Konfiguration."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models


@dataclass
class EscalationSettings:
    enabled: bool = False
    default_sla_days: int = 14
    interval_minutes: int = 60
    reminder_percent: int = 80
    bereichsleiter_role: str = "Bereichsleiter"


def get_escalation_settings(db: Session) -> EscalationSettings:
    cfg = db.get(models.EscalationConfig, 1)
    if cfg is None:
        return EscalationSettings()
    role_name = "Bereichsleiter"
    if cfg.bereichsleiter_role_id:
        role = db.get(models.Role, cfg.bereichsleiter_role_id)
        if role:
            role_name = role.name
    return EscalationSettings(
        enabled=cfg.enabled,
        default_sla_days=cfg.default_sla_days,
        interval_minutes=cfg.interval_minutes,
        reminder_percent=cfg.reminder_percent,
        bereichsleiter_role=role_name,
    )
