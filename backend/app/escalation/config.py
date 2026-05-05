"""Settings fuer SLA-Eskalation."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EscalationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    escalation_enabled: bool = False
    escalation_default_sla_days: int = 14
    escalation_interval_minutes: int = 60
    # An welche Rolle eskalieren wir, wenn das SLA reisst und die Stage-Rolle
    # nicht reagiert hat?
    escalation_bereichsleiter_role: str = "Bereichsleiter"


@lru_cache(maxsize=1)
def get_escalation_settings() -> EscalationSettings:
    return EscalationSettings()


def reset_escalation_settings_cache() -> None:
    get_escalation_settings.cache_clear()
