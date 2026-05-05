"""Tests fuer Dashboard-Stats und Archiv-Filter (Commit 4)."""
from __future__ import annotations

from .conftest import auth_header, login_as


def _create_and_submit(client, admin_auth, schema_typ: str, daten: dict) -> str:
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == schema_typ and d["status"] == "active")
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": daten}, headers=admin_auth)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    return iid


def test_stats_endpoint_returns_expected_shape(client, admin_auth):
    r = client.get("/instances/stats", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    for key in (
        "status_counts", "stage_counts", "waiting_for_me",
        "own_instances", "last7_created", "last7_decided", "avg_decision_days",
    ):
        assert key in body


def test_filter_status_in(client, admin_auth):
    r = client.get("/instances?status=entwurf", headers=admin_auth)
    assert r.status_code == 200
    for i in r.json():
        assert i["status"] == "entwurf"


def test_filter_typ_and_version(client, admin_auth):
    r = client.get("/instances?typ=Vorstandsbeschluss", headers=admin_auth)
    assert r.status_code == 200
    for i in r.json():
        assert i["schema_version"].startswith("Vorstandsbeschluss/")


def test_filter_mein_only_owns(client):
    """Loggt einen Standard-User ein, legt einen Antrag an, prueft Filter `mein`."""
    fb = login_as(client, "fachbereich")
    headers = auth_header(fb)

    # Anlegen eines AT-8.2-Antrags durch fachbereich
    valid = {
        "antragsteller": {"name": "FB", "abteilung": "IT", "datum": "2026-05-05"},
        "vorhaben": {"titel": "Cloud Storage Pilot", "kategorie": "IT-System"},
        "wesentlichkeitskriterien": {
            "ertragsrelevanz": "mittel", "risikorelevanz": "mittel",
            "aufsichtsrechtlicheRelevanz": True, "doraRelevanz": True,
        },
        "ergebnis": {
            "wesentlich": True,
            "begruendung": "Mindestens 50 Zeichen Begruendung mit ausreichend Inhalt fuer das Schema.",
        },
    }
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": valid}, headers=headers)
    assert r.status_code == 201

    # Mit Filter "mein" duerfen wir nur unsere eigenen sehen
    r = client.get("/instances?mein=true", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert all(i["antragsteller"] == "fachbereich" for i in body)
    assert any(i["antragsteller"] == "fachbereich" for i in body)


def test_filter_wartet_auf_mich(client):
    """User mit Rolle Vorstand: wartet_auf_mich darf nur in_pruefung-Antraege liefern,
    deren Stage-Rolle Vorstand ist."""
    vorstand = login_as(client, "vorstand")
    headers = auth_header(vorstand)
    r = client.get("/instances?wartet_auf_mich=true", headers=headers)
    assert r.status_code == 200
    for i in r.json():
        assert i["status"] == "in_pruefung"
        # Pro Antrag: aktuelle_stage hat eine "rolle", die in unseren Rollen ist
        stage = next(s for s in i["workflow_stages"] if s["name"] == i["aktuelle_stage"])
        assert stage["rolle"] == "Vorstand"


def test_csv_export(client, admin_auth):
    r = client.get("/instances?format=csv", headers=admin_auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    # Erste Zeile ist die Header-Zeile
    head = text.splitlines()[0]
    assert "schema_typ" in head and "antragsteller" in head and "status" in head


def test_filter_created_to_excludes_recent(client, admin_auth):
    """created_to weit in der Vergangenheit -> leere Liste."""
    r = client.get("/instances?created_to=2000-01-01T00:00:00Z", headers=admin_auth)
    assert r.status_code == 200
    assert r.json() == []
