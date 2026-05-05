"""SLA-Eskalation: zwei Stufen, Idempotenz, Stage-Wechsel-Reset.

Wir manipulieren stage_eingetreten_am direkt in der DB (anstatt zu warten),
damit der Scanner SLA-Verstoesse erkennt. SMTP- und Eskalations-Konfiguration
liegen seit dem Admin-Panel in der DB — die Fixtures setzen sie dort.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
def enable_notifications_and_escalation():
    from app import models
    from app.database import SessionLocal

    with SessionLocal() as db:
        smtp = db.get(models.SmtpConfig, 1) or models.SmtpConfig(id=1)
        if not db.get(models.SmtpConfig, 1):
            db.add(smtp)
        smtp.enabled = True
        smtp.mail_from = "noreply@bws.test"

        esc = db.get(models.EscalationConfig, 1) or models.EscalationConfig(id=1)
        if not db.get(models.EscalationConfig, 1):
            db.add(esc)
        esc.enabled = True
        esc.default_sla_days = 10
        esc.interval_minutes = 60
        db.commit()
    yield
    with SessionLocal() as db:
        smtp = db.get(models.SmtpConfig, 1)
        if smtp:
            smtp.enabled = False
        esc = db.get(models.EscalationConfig, 1)
        if esc:
            esc.enabled = False
        db.commit()


@pytest.fixture
def captured_mails():
    captured: list[dict] = []

    def fake(*, to, subject, body, db=None):
        captured.append({"to": list(to), "subject": subject, "body": body})

    with patch("app.notifications.smtp.send_email", new=fake):
        with patch("app.escalation.scanner.send_email", new=fake):
            with patch("app.notifications.dispatcher.send_email", new=fake):
                yield captured


def _create_in_review_instance(client, admin_auth) -> str:
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    daten = {
        "antragsteller": {"name": "T", "abteilung": "IT", "datum": "2026-05-05"},
        "vorhaben": {"titel": "SLA-Test", "kategorie": "IT-System"},
        "wesentlichkeitskriterien": {
            "ertragsrelevanz": "mittel", "risikorelevanz": "mittel",
            "aufsichtsrechtlicheRelevanz": True, "doraRelevanz": True,
        },
        "ergebnis": {
            "wesentlich": True,
            "begruendung": "Hinreichend langer Begruendungstext, der das Mindestlimit ueberschreitet.",
        },
    }
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": daten}, headers=admin_auth)
    iid = r.json()["id"]
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    return iid


def _backdate_stage(instance_id: str, days_ago: float) -> None:
    from app.database import SessionLocal
    from app.models import FormInstance
    with SessionLocal() as db:
        inst = db.get(FormInstance, instance_id)
        inst.stage_eingetreten_am = datetime.now(timezone.utc) - timedelta(days=days_ago)
        inst.erinnerung_sent_at = None
        inst.eskalation_sent_at = None
        db.commit()


def test_no_action_when_below_half_sla(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=1)
    captured_mails.clear()
    from app.escalation.scanner import scan_once
    counts = scan_once()
    assert counts["erinnerungen"] == 0
    assert counts["eskalationen"] == 0


def test_erinnerung_at_half_sla(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=6)
    captured_mails.clear()
    from app.escalation.scanner import scan_once
    counts = scan_once()
    assert counts["erinnerungen"] >= 1
    assert any("Erinnerung" in m["subject"] for m in captured_mails), [m["subject"] for m in captured_mails]


@pytest.mark.fachlich(
    anforderung="MaRisk AT 4.3.4 — Eskalation bei ueberschrittenem SLA",
    soll="Antrag, der laenger als das Stage-SLA in einer Stage haengt, loest die Stufe-2-Eskalation an den Bereichsleiter aus.",
)
def test_eskalation_after_sla_breach(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=11)
    captured_mails.clear()
    from app.escalation.scanner import scan_once
    counts = scan_once()
    assert counts["eskalationen"] >= 1
    assert any("ESKALATION" in m["subject"] for m in captured_mails), [m["subject"] for m in captured_mails]


def test_idempotenz_zweiter_scan_macht_nichts(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=11)
    captured_mails.clear()
    from app.escalation.scanner import scan_once
    first = scan_once()
    second = scan_once()
    assert first["eskalationen"] >= 1
    assert second["eskalationen"] == 0


def test_stage_wechsel_setzt_sla_zurueck(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=11)
    from app.escalation.scanner import scan_once
    scan_once()
    captured_mails.clear()
    client.post(f"/instances/{iid}/decide", json={"entscheidung": "approved"}, headers=admin_auth)
    counts = scan_once()
    assert counts["erinnerungen"] == 0
    assert counts["eskalationen"] == 0


def test_audit_log_records_sla_actions(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=11)
    from app.escalation.scanner import scan_once
    scan_once()
    r = client.get("/admin/audit?kategorie=instance", headers=admin_auth)
    actions = {e["action"] for e in r.json()}
    assert "sla.eskalation" in actions


def test_disabled_no_scheduler():
    """Bei DB-config.enabled=False darf der Scheduler nicht starten."""
    from app import models
    from app.database import SessionLocal
    from app.escalation import scheduler

    with SessionLocal() as db:
        cfg = db.get(models.EscalationConfig, 1) or models.EscalationConfig(id=1)
        if not db.get(models.EscalationConfig, 1):
            db.add(cfg)
        cfg.enabled = False
        db.commit()
    scheduler.stop()
    scheduler.start_from_db()
    assert scheduler._scheduler is None
