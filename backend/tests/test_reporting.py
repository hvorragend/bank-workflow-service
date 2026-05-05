"""Reporting-Endpunkte mit X-Reporting-Token-Auth."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _create_token(client, admin_auth, name: str = "Test-Token") -> str:
    r = client.post("/admin/reporting-tokens",
                    json={"name": name},
                    headers=admin_auth)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_reporting_token_create_returns_klartext_once(client, admin_auth):
    r = client.post("/admin/reporting-tokens",
                    json={"name": "Aufsicht 2026"},
                    headers=admin_auth)
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("bws_")
    assert "_warning" in body  # Token ist nur einmal sichtbar


def test_reporting_endpoint_without_token_returns_401(client):
    r = client.get("/reporting/aggregates/quarterly")
    assert r.status_code == 401


@pytest.mark.fachlich(
    anforderung="MaRisk AT 4.3.4 — separater Reporting-Zugang fuer Aufsicht",
    soll="Reporting-Endpunkte sind ueber eigenen API-Token erreichbar; ein User-JWT reicht NICHT.",
)
def test_reporting_endpoint_with_jwt_only_returns_401(client, admin_auth):
    """Selbst ein JWT-Token (User-Login) darf nicht reichen — der Reporting-Pfad
    erwartet X-Reporting-Token."""
    r = client.get("/reporting/aggregates/quarterly", headers=admin_auth)
    assert r.status_code == 401


def test_reporting_endpoint_with_valid_token(client, admin_auth):
    token = _create_token(client, admin_auth)
    r = client.get("/reporting/aggregates/quarterly",
                   headers={"X-Reporting-Token": token})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reporting_aggregates_duration(client, admin_auth):
    token = _create_token(client, admin_auth)
    r = client.get("/reporting/aggregates/duration",
                   headers={"X-Reporting-Token": token})
    assert r.status_code == 200
    body = r.json()
    # Mindestens der geseedete genehmigte AT-8.2-Antrag sollte in den Aggregaten erscheinen
    assert any(item["typ"] == "AT_8_2_Analyse" for item in body)


def test_reporting_full_instance_returns_audit_trail(client, admin_auth):
    token = _create_token(client, admin_auth)
    # Nimm den geseedeten genehmigten Antrag
    insts = client.get("/instances?status=genehmigt", headers=admin_auth).json()
    assert insts, "Erwartet mind. einen genehmigten Antrag aus dem Seed."
    iid = insts[0]["id"]

    r = client.get(f"/reporting/instances/{iid}",
                   headers={"X-Reporting-Token": token})
    assert r.status_code == 200
    body = r.json()
    # Vollstaendig: Daten, Schema, Approvals
    assert "schema" in body and "approvals" in body
    assert len(body["approvals"]) > 0


def test_revoked_token_is_rejected(client, admin_auth):
    token = _create_token(client, admin_auth, name="Bald-widerrufen")
    # Liste holen, ID herausfinden
    rows = client.get("/admin/reporting-tokens", headers=admin_auth).json()
    target = [r for r in rows if r["name"] == "Bald-widerrufen"][0]

    r = client.delete(f"/admin/reporting-tokens/{target['id']}", headers=admin_auth)
    assert r.status_code == 204

    r = client.get("/reporting/aggregates/quarterly",
                   headers={"X-Reporting-Token": token})
    assert r.status_code == 401


def test_non_admin_cannot_create_reporting_token(client):
    from .conftest import auth_header, login_as
    fb = login_as(client, "fachbereich")
    r = client.post("/admin/reporting-tokens", json={"name": "x"}, headers=auth_header(fb))
    assert r.status_code == 403
