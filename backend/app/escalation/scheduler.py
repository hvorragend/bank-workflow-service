"""APScheduler-Singleton: startet beim App-Lifespan, faehrt beim Shutdown sauber runter.

Kapselt eine Hintergrund-Aufgabe, die periodisch scan_once aufruft.
Wenn ESCALATION_ENABLED=False (Default), startet der Scheduler nicht — Tests
und Quickstart sind unbeeinflusst.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import get_escalation_settings
from .scanner import scan_once

log = logging.getLogger("escalation.scheduler")

_scheduler: BackgroundScheduler | None = None


def start() -> None:
    global _scheduler
    s = get_escalation_settings()
    if not s.escalation_enabled:
        log.info("ESCALATION_ENABLED=False — Scheduler nicht gestartet.")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _safe_scan,
        "interval",
        minutes=s.escalation_interval_minutes,
        id="sla_scan",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("SLA-Scheduler gestartet (Intervall %d Minuten).", s.escalation_interval_minutes)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _safe_scan() -> None:
    try:
        counts = scan_once()
        log.info("SLA-Scan: %s", counts)
    except Exception as e:  # noqa: BLE001
        log.exception("SLA-Scan fehlgeschlagen: %s", e)
