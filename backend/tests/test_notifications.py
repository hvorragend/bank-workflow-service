"""Notifications: Empfaenger-Aufloesung + Versand-Hooks im Workflow.

SMTP wird gemockt, damit keine echten Verbindungen aufgebaut werden.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from .conftest import approve_one, auth_header, login_as, reject_one


@pytest.fixture
def enable_notifications():
    """Aktiviert SMTP in der DB-Config (smtp_config-Row id=1, enabled=True)."""
    from app.database import SessionLocal
    from app import models

    with SessionLocal() as db:
        cfg = db.get(models.SmtpConfig, 1)
        if cfg is None:
            cfg = models.SmtpConfig(id=1)
            db.add(cfg)
        cfg.enabled = True
        cfg.mail_from = "noreply@bws.test"
        db.commit()
    yield
    with SessionLocal() as db:
        cfg = db.get(models.SmtpConfig, 1)
        if cfg:
            cfg.enabled = False
            db.commit()


@pytest.fixture
def captured_mails():
    captured: list[dict] = []

    def fake_send(*, to, subject, body, db=None):
        captured.append({"to": list(to), "subject": subject, "body": body})

    with patch("app.notifications.smtp.send_email", new=fake_send):
        with patch("app.notifications.dispatcher.send_email", new=fake_send):
            yield captured


def test_emails_for_role_uses_db_users():
    """Test-User aus conftest sind in der DB — die Rolle Vorstand kennt eine Adresse."""
    from app.notifications.recipients import emails_for_role
    addrs = emails_for_role("Vorstand")
    assert any("vorstand" in a for a in addrs), addrs


def test_submit_triggers_stage_pending_mail(client, admin_auth, enable_notifications, captured_mails):
    drafts = client.get("/instances?status=entwurf", headers=admin_auth).json()
    assert drafts, "Erwartet mind. einen Entwurf aus dem Seed."
    iid = drafts[0]["id"]

    r = client.post(f"/instances/{iid}/submit", headers=admin_auth)
    assert r.status_code == 200
    assert captured_mails, "Erwartet eine Stage-Pending-Mail nach dem Submit."
    subjects = [m["subject"] for m in captured_mails]
    assert any("wartet" in s.lower() for s in subjects), subjects


def test_full_chain_sends_approved_mail_at_end(client, admin_auth, enable_notifications, captured_mails):
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    daten = {
        "antragsteller": {"name": "Test", "abteilung": "IT", "datum": "2026-05-05"},
        "vorhaben": {"titel": "Notification-Smoke", "kategorie": "IT-System"},
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

    # Drei Approvals durchklicken (admin hat alle Rollen) — AT-8.2 ist linear.
    for _ in range(3):
        approve_one(client, admin_auth, iid)

    assert any("Genehmigt" in m["subject"] for m in captured_mails), \
        [m["subject"] for m in captured_mails]


def test_rejection_mails_antragsteller(client, admin_auth, enable_notifications, captured_mails):
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    daten = {
        "antragsteller": {"name": "X", "abteilung": "Y", "datum": "2026-05-05"},
        "vorhaben": {"titel": "Reject-Test", "kategorie": "IT-System"},
        "wesentlichkeitskriterien": {
            "ertragsrelevanz": "niedrig", "risikorelevanz": "niedrig",
            "aufsichtsrechtlicheRelevanz": False, "doraRelevanz": False,
        },
        "ergebnis": {
            "wesentlich": False,
            "begruendung": "Hinreichend langer Begruendungstext, der das Mindestlimit ueberschreitet.",
        },
    }
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": daten}, headers=admin_auth)
    iid = r.json()["id"]
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    captured_mails.clear()
    reject_one(client, admin_auth, iid, kommentar="Nicht hinreichend dokumentiert.")

    assert any("Abgelehnt" in m["subject"] for m in captured_mails), \
        [m["subject"] for m in captured_mails]


def test_notifications_disabled_no_mails_sent(client, admin_auth):
    """Ohne enabled in der DB-Config darf nichts geschickt werden."""
    captured: list[dict] = []

    def fake_send(*, to, subject, body, db=None):
        captured.append({"to": to, "subject": subject})

    with patch("app.notifications.smtp.send_email", new=fake_send):
        drafts = client.get("/instances?status=entwurf", headers=admin_auth).json()
        if drafts:
            client.post(f"/instances/{drafts[0]['id']}/submit", headers=admin_auth)
    assert captured == []
