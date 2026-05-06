"""APScheduler-Singleton fuer den SLA-Scanner. Konfiguration aus DB.

Beim App-Start wird einmal `start_from_db()` aufgerufen — der Scheduler liest
die aktuelle escalation_config-Row und startet sich, falls enabled=True.

Aenderungen ueber das Admin-Panel rufen `reload_from_db()`, das je nach
neuem Stand startet, stoppt oder das Intervall neu setzt.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from ..config_service.escalation_settings import EscalationSettings, get_escalation_settings
from ..database import SessionLocal
from .scanner import scan_once

log = logging.getLogger("escalation.scheduler")

_scheduler: BackgroundScheduler | None = None
_current_interval: int | None = None


def _safe_scan() -> None:
    try:
        counts = scan_once()
        log.info("SLA-Scan: %s", counts)
    except Exception as e:  # noqa: BLE001
        log.exception("SLA-Scan fehlgeschlagen: %s", e)


def _start_with(settings: EscalationSettings) -> None:
    global _scheduler, _current_interval
    if not settings.enabled:
        log.info("Eskalation deaktiviert — Scheduler bleibt aus.")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _safe_scan,
        "interval",
        minutes=settings.interval_minutes,
        id="sla_scan",
        replace_existing=True,
    )
    _scheduler.start()
    _current_interval = settings.interval_minutes
    log.info("SLA-Scheduler gestartet (Intervall %d Minuten).", settings.interval_minutes)


def start_from_db() -> None:
    """Wird im App-Lifespan aufgerufen."""
    with SessionLocal() as db:
        _start_with(get_escalation_settings(db))


def reload_from_db() -> None:
    """Wird vom Admin-Endpoint nach Save aufgerufen. Idempotent."""
    global _scheduler, _current_interval
    with SessionLocal() as db:
        settings = get_escalation_settings(db)

    if not settings.enabled:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            _current_interval = None
            log.info("SLA-Scheduler gestoppt (per Admin-Aktion).")
        return

    if _scheduler is None:
        _start_with(settings)
        return

    if _current_interval != settings.interval_minutes:
        _scheduler.reschedule_job(
            "sla_scan", trigger="interval", minutes=settings.interval_minutes,
        )
        _current_interval = settings.interval_minutes
        log.info("SLA-Scheduler-Intervall geaendert: %d Minuten.", settings.interval_minutes)


def stop() -> None:
    global _scheduler, _current_interval
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        _current_interval = None


# Backwards-Compat fuer main.lifespan, das bisher start()/stop() rief.
def start() -> None:
    start_from_db()
