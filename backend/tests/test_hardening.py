"""Regressionstests fuer Härtungs-Findings F-007 (Definition-Validierung) und
F-008 (Refresh gleicht Kontostatus gegen die DB ab)."""
from __future__ import annotations

from .conftest import TEST_PASSWORD


def test_create_definition_rejects_cyclic_graph(client, admin_auth):
    """Ein Workflow-Graph mit Zyklus/ohne gueltige Struktur wird mit 422
    abgelehnt statt persistiert und spaeter als 500/RecursionError zu knallen."""
    bad = {
        "typ": "Test_Bad",
        "version": "9.9.9",
        "titel": "Kaputt",
        "json_schema": {"type": "object"},
        "ui_schema": {"type": "VerticalLayout", "elements": []},
        "workflow_graph": {"nodes": [], "edges": []},  # keine Knoten -> ungueltig
        "erstellt_von": "admin",
    }
    r = client.post("/definitions", json=bad, headers=admin_auth)
    assert r.status_code == 422, r.text


def test_create_definition_rejects_invalid_json_schema(client, admin_auth):
    bad = {
        "typ": "Test_Bad2",
        "version": "9.9.8",
        "titel": "Kaputt",
        # 'type' als Zahl ist kein gueltiges JSON-Schema
        "json_schema": {"type": 123},
        "ui_schema": {"type": "VerticalLayout", "elements": []},
        "workflow_graph": {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "t1", "type": "user_task", "rolle": "Vorstand", "label": "T1"},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "t1"},
                {"from": "t1", "to": "end"},
            ],
        },
        "erstellt_von": "admin",
    }
    r = client.post("/definitions", json=bad, headers=admin_auth)
    assert r.status_code == 422, r.text


def _set_active(username: str, active: bool) -> None:
    from sqlalchemy import select
    from app import models
    from app.database import SessionLocal
    with SessionLocal() as db:
        u = db.scalar(select(models.User).where(models.User.username == username))
        u.is_active = active
        db.commit()


def test_deactivated_user_cannot_refresh(client):
    """Wird ein User deaktiviert, darf sein (kryptografisch noch gueltiger)
    Refresh-Cookie keine neuen Access-Tokens mehr liefern (F-008)."""
    r = client.post("/auth/login", json={"username": "risiko", "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    cookie = client.cookies.get("bws_refresh")
    assert cookie

    # Vor Deaktivierung: Refresh funktioniert.
    assert client.post("/auth/refresh", cookies={"bws_refresh": cookie}).status_code == 200

    _set_active("risiko", False)
    try:
        r = client.post("/auth/refresh", cookies={"bws_refresh": cookie})
        assert r.status_code == 401, r.text
    finally:
        _set_active("risiko", True)  # andere Tests nicht stoeren
