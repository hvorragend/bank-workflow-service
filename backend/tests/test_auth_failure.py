"""Negativtests: falsche Credentials, fehlender Token, abgelaufener Token, fehlende Rolle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from .conftest import TEST_PASSWORD, auth_header, login_as


def test_login_with_wrong_password_returns_401(client):
    r = client.post("/auth/login", json={"username": "vorstand", "password": "wrong"})
    assert r.status_code == 401
    # Generische Fehlermeldung — keine Hinweise, ob User existiert oder nicht.
    assert "ungueltig" in r.json()["detail"].lower()


def test_login_with_unknown_user_returns_401(client):
    r = client.post("/auth/login", json={"username": "ghost-user", "password": "egal"})
    assert r.status_code == 401


def test_protected_endpoint_without_token_returns_401(client):
    r = client.get("/instances")
    assert r.status_code == 401


def test_protected_endpoint_with_garbage_token_returns_401(client):
    r = client.get("/instances", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401(client):
    """Wir bauen ein abgelaufenes Token mit dem Test-Secret und schicken es."""
    import os
    secret = os.environ["JWT_SECRET"]
    payload = {
        "sub": "admin",
        "name": "Test admin",
        "email": "admin@test.local",
        "roles": ["Admin"],
        "auth_source": "local",
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
        "type": "access",
    }
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    r = client.get("/instances", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "abgelaufen" in r.json()["detail"].lower()


def test_admin_only_endpoint_blocks_non_admin(client):
    """POST /definitions verlangt die Rolle Admin — `vorstand` hat sie nicht."""
    token = login_as(client, "vorstand")
    r = client.post(
        "/definitions",
        headers=auth_header(token),
        json={
            "typ": "Test", "version": "0.0.1", "titel": "Test",
            "json_schema": {"type": "object"}, "ui_schema": {}, "workflow_stages": [],
            "erstellt_von": "vorstand",
        },
    )
    assert r.status_code == 403


def test_decide_with_wrong_role_returns_403(client, admin_auth):
    """User ohne Vorstand-Rolle darf den Vorstandsbeschluss nicht in der Vorstand-Stage genehmigen."""
    # Admin (alle Rollen) legt einen Antrag an und treibt ihn bis zur Vorstand-Stage.
    defs = client.get("/definitions").json()
    vb = next(d for d in defs if d["typ"] == "Vorstandsbeschluss" and d["status"] == "active")

    daten = {
        "beschluss": {
            "titel": "Test-Beschluss fuer Rollen-Negativtest",
            "datum": "2026-12-01",
            "vorlagengeber": "Test",
            "kategorie": "Sonstiges",
        },
        "antrag": {
            "sachverhalt": (
                "Reiner Testfall fuer die Pruefung der Rollen-Validierung im Workflow. "
                "Wir wollen sehen, dass ein User ohne die zur Stage gehoerende Rolle "
                "abgewiesen wird, auch wenn er authentifiziert ist."
            ),
            "begruendung": (
                "Damit auditierbar bleibt, dass der Stage-Rollen-Check tatsaechlich greift "
                "und nicht nur eine UI-Garantie ist, sondern serverseitig in der Workflow-"
                "Engine erzwungen wird."
            ),
        },
        "beschlussvorschlag": {"wortlaut": "Der Vorstand beschliesst: nichts. Reiner Test."},
        "marisk_relevanz": {
            "at_9_auslagerung": False, "at_7_2_it_systeme": False,
            "dora_ikt_risiko": False, "npp_neue_produkte": False,
            "at_8_2_wesentlich": False,
        },
    }
    r = client.post("/instances", json={"form_definition_id": vb["id"], "daten": daten}, headers=admin_auth)
    assert r.status_code == 201
    iid = r.json()["id"]

    # Admin treibt den Antrag bis zur Vorstand-Stage durch.
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    for _ in range(2):  # vorbereitung, rechtskonformitaet
        client.post(f"/instances/{iid}/decide", json={"entscheidung": "approved"}, headers=admin_auth)

    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert state["aktuelle_stage"] == "vorstand"

    # Jetzt versucht ein User ohne Vorstand-Rolle die Genehmigung — muss 403 geben.
    fb_token = login_as(client, "fachbereich")
    r = client.post(
        f"/instances/{iid}/decide",
        json={"entscheidung": "approved"},
        headers=auth_header(fb_token),
    )
    assert r.status_code == 403
    assert "Rolle" in r.json()["detail"]
