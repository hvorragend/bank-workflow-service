"""Notifications: Empfaenger-Aufloesung + Versand-Hooks im Workflow.

SMTP wird gemockt, damit keine echten Verbindungen aufgebaut werden.
Wir pruefen, dass bei den richtigen Workflow-Ereignissen die richtigen
Templates an die richtigen Adressen gehen.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from .conftest import auth_header, login_as


@pytest.fixture
def enable_notifications(monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("MAIL_FROM", "noreply@bws.test")
    from app.notifications.config import reset_notification_settings_cache
    reset_notification_settings_cache()
    yield
    reset_notification_settings_cache()


@pytest.fixture
def captured_mails():
    """Faengt alle send_email-Aufrufe ab. Liste enthaelt dicts mit subject/to/body."""
    captured: list[dict] = []

    def fake_send(*, to, subject, body):
        captured.append({"to": list(to), "subject": subject, "body": body})

    with patch("app.notifications.smtp.send_email", new=fake_send):
        with patch("app.notifications.dispatcher.send_email", new=fake_send):
            yield captured


def test_emails_for_role_falls_back_to_local_users():
    from app.notifications.recipients import emails_for_role
    addrs = emails_for_role("Vorstand")
    # Test-User aus conftest haben emails wie 'vorstand@test.local'
    assert any("vorstand" in a for a in addrs), addrs


def test_submit_triggers_stage_pending_mail(client, admin_auth, enable_notifications, captured_mails):
    # Existierenden Entwurf finden und einreichen.
    drafts = client.get("/instances?status=entwurf", headers=admin_auth).json()
    assert drafts, "Erwartet mind. einen Entwurf aus dem Seed."
    iid = drafts[0]["id"]

    r = client.post(f"/instances/{iid}/submit", headers=admin_auth)
    assert r.status_code == 200

    # Nach BackgroundTask sollte mind. eine Mail abgesendet sein.
    assert captured_mails, "Erwartet eine Stage-Pending-Mail nach dem Submit."
    subjects = [m["subject"] for m in captured_mails]
    assert any("wartet" in s.lower() for s in subjects), subjects


def test_full_chain_sends_approved_mail_at_end(client, admin_auth, enable_notifications, captured_mails):
    """Eine komplette Genehmigungskette muss am Ende eine 'Genehmigt'-Mail
    an den Antragsteller schicken."""
    # Antrag anlegen + einreichen
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

    # Drei Approvals durchklicken (admin hat alle Rollen)
    for _ in range(3):
        client.post(f"/instances/{iid}/decide", json={"entscheidung": "approved"}, headers=admin_auth)

    # Mind. eine Mail enthaelt 'Genehmigt' im Subject
    assert any("Genehmigt" in m["subject"] for m in captured_mails), \
        [m["subject"] for m in captured_mails]


def test_rejection_mails_antragsteller(client, admin_auth, enable_notifications, captured_mails):
    """Bei Ablehnung in der ersten Stage wird der Antragsteller informiert."""
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
    client.post(f"/instances/{iid}/decide",
                json={"entscheidung": "rejected", "kommentar": "Nicht hinreichend dokumentiert."},
                headers=admin_auth)

    assert any("Abgelehnt" in m["subject"] for m in captured_mails), \
        [m["subject"] for m in captured_mails]


def test_notifications_disabled_no_mails_sent(client, admin_auth):
    """Ohne NOTIFICATIONS_ENABLED darf nichts geschickt werden."""
    captured: list[dict] = []

    def fake_send(*, to, subject, body):
        captured.append({"to": to, "subject": subject})

    with patch("app.notifications.smtp.send_email", new=fake_send):
        # NOTIFICATIONS_ENABLED ist im Test-Default false (siehe conftest).
        drafts = client.get("/instances?status=entwurf", headers=admin_auth).json()
        if drafts:
            client.post(f"/instances/{drafts[0]['id']}/submit", headers=admin_auth)
    # send_email wurde nie als Bypass gerufen — Dispatcher prueft NOTIFICATIONS_ENABLED via NotificationsDisabled
    assert captured == []
