"""SLA-Eskalation: zwei Stufen, Idempotenz, Stage-Wechsel-Reset.

Wir manipulieren stage_eingetreten_am direkt in der DB (anstatt zu warten),
damit der Scanner SLA-Verstoesse erkennt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from .conftest import TEST_PASSWORD, login_as


@pytest.fixture
def enable_notifications_and_escalation(monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("ESCALATION_ENABLED", "true")
    monkeypatch.setenv("ESCALATION_DEFAULT_SLA_DAYS", "10")
    monkeypatch.setenv("MAIL_FROM", "noreply@bws.test")
    from app.notifications.config import reset_notification_settings_cache
    from app.escalation.config import reset_escalation_settings_cache
    reset_notification_settings_cache()
    reset_escalation_settings_cache()
    yield
    reset_notification_settings_cache()
    reset_escalation_settings_cache()


@pytest.fixture
def captured_mails():
    captured: list[dict] = []

    def fake(*, to, subject, body):
        captured.append({"to": list(to), "subject": subject, "body": body})

    with patch("app.notifications.smtp.send_email", new=fake):
        with patch("app.escalation.scanner.send_email", new=fake):
            with patch("app.notifications.dispatcher.send_email", new=fake):
                yield captured


def _create_in_review_instance(client, admin_auth) -> str:
    """Antrag anlegen und einreichen, sodass er in_pruefung @ erste Stage steht."""
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
    """Setzt stage_eingetreten_am zurueck, ohne den Scanner zu durchlaufen."""
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
    _backdate_stage(iid, days_ago=1)  # SLA = 10, halb = 5 — 1 Tag liegt deutlich darunter
    captured_mails.clear()

    from app.escalation.scanner import scan_once
    counts = scan_once()

    assert counts["erinnerungen"] == 0
    assert counts["eskalationen"] == 0


def test_erinnerung_at_half_sla(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=6)  # SLA = 10, halb = 5 — 6 Tage > 5
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
    _backdate_stage(iid, days_ago=11)  # SLA = 10 — ueberschritten
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
    assert second["eskalationen"] == 0  # nicht erneut eskalieren


def test_stage_wechsel_setzt_sla_zurueck(client, admin_auth, enable_notifications_and_escalation, captured_mails):
    iid = _create_in_review_instance(client, admin_auth)
    _backdate_stage(iid, days_ago=11)

    from app.escalation.scanner import scan_once
    scan_once()  # eskaliert

    # Admin entscheidet: approved -> naechste Stage. SLA muss zuruecksetzen.
    captured_mails.clear()
    client.post(f"/instances/{iid}/decide", json={"entscheidung": "approved"}, headers=admin_auth)

    # Direkt nach Stage-Wechsel keine Mahnung
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


def test_disabled_no_scheduler(monkeypatch):
    """Bei ESCALATION_ENABLED=False darf der Scheduler nicht starten."""
    monkeypatch.setenv("ESCALATION_ENABLED", "false")
    from app.escalation import scheduler
    from app.escalation.config import reset_escalation_settings_cache
    reset_escalation_settings_cache()
    scheduler.stop()  # idempotent
    scheduler.start()
    assert scheduler._scheduler is None
