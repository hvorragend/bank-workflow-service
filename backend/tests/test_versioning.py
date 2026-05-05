"""End-to-end smoke test that proves the versioning guarantee:

- Create instance against v1 (which has 3 wesentlichkeitskriterien fields).
- Activate v2 (which adds doraRelevanz as a 4th REQUIRED field).
- Old v1 instance must remain valid against its pinned v1 schema.
- New instance against v2 must require doraRelevanz.

Run with:  pytest tests/
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Isolated DB file for this test run
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # Import AFTER env var is set
    from app.main import app  # noqa: WPS433
    with TestClient(app) as c:
        yield c

    os.unlink(db_path)


VALID_V1_DATA = {
    "antragsteller": {
        "name": "Carsten Volmer",
        "abteilung": "IT-Sicherheit",
        "datum": "2026-05-05",
    },
    "vorhaben": {
        "titel": "Einführung neuer Cloud-Storage",
        "kategorie": "IT-System",
    },
    "wesentlichkeitskriterien": {
        "ertragsrelevanz": "mittel",
        "risikorelevanz": "hoch",
        "aufsichtsrechtlicheRelevanz": True,
    },
    "ergebnis": {
        "wesentlich": True,
        "begruendung": (
            "Das System verarbeitet personenbezogene und kundenbezogene Daten "
            "und unterliegt erhöhten aufsichtsrechtlichen Anforderungen."
        ),
    },
}


def test_seeded_definitions_present(client):
    r = client.get("/definitions", params={"typ": "AT_8_2_Analyse"})
    assert r.status_code == 200
    versions = {d["version"]: d["status"] for d in r.json()}
    assert versions == {"1.0.0": "retired", "2.0.0": "active"}


def test_create_instance_against_active_v2_requires_dora(client):
    v2_id = _find_definition(client, "2.0.0")
    # Without doraRelevanz → must fail
    r = client.post(
        "/instances",
        json={
            "form_definition_id": v2_id,
            "daten": VALID_V1_DATA,  # missing doraRelevanz
            "antragsteller": "test.user",
        },
    )
    assert r.status_code == 422
    assert "doraRelevanz" in r.json()["detail"]


def test_old_v1_instance_stays_valid_after_v2_activation(client):
    """The whole point: an instance created against v1 must keep working,
    even though v2 introduces new required fields.
    """
    # Force-activate v1 temporarily so we can create against it
    v1_id = _find_definition(client, "1.0.0")
    v2_id = _find_definition(client, "2.0.0")
    _set_status(client, v1_id, target="active", deactivate_id=v2_id)

    # Create v1 instance (no doraRelevanz needed)
    r = client.post(
        "/instances",
        json={
            "form_definition_id": v1_id,
            "daten": VALID_V1_DATA,
            "antragsteller": "test.user",
        },
    )
    assert r.status_code == 201, r.text
    instance_id = r.json()["id"]

    # Re-activate v2 (retires v1 again)
    _set_status(client, v2_id, target="active", deactivate_id=v1_id)

    # Old v1 instance: still readable, still valid against its pinned v1 schema
    r = client.get(f"/instances/{instance_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "AT_8_2_Analyse/1.0.0"
    # And its schema does NOT contain the v2 doraRelevanz field
    krit = body["json_schema"]["properties"]["wesentlichkeitskriterien"]["properties"]
    assert "doraRelevanz" not in krit


def test_full_approval_chain(client):
    v2_id = _find_definition(client, "2.0.0")
    daten = {**VALID_V1_DATA}
    daten["wesentlichkeitskriterien"] = {
        **daten["wesentlichkeitskriterien"],
        "doraRelevanz": True,
    }

    r = client.post(
        "/instances",
        json={"form_definition_id": v2_id, "daten": daten, "antragsteller": "carsten"},
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    assert client.post(f"/instances/{iid}/submit").json()["aktuelle_stage"] == "fachbereich"

    for stage_name, rolle in [
        ("fachbereich", "Fachbereichsleiter"),
        ("risikomgmt",  "Risikomanagement"),
        ("vorstand",    "Vorstand"),
    ]:
        r = client.post(
            f"/instances/{iid}/decide",
            json={
                "genehmiger": f"user_{stage_name}",
                "rolle": rolle,
                "entscheidung": "approved",
                "kommentar": f"OK von {rolle}",
            },
        )
        assert r.status_code == 200, r.text

    final = client.get(f"/instances/{iid}").json()
    assert final["status"] == "genehmigt"
    assert len(final["approvals"]) == 3
    assert all(a["entscheidung"] == "approved" for a in final["approvals"])


# --- helpers ---

def _find_definition(client, version: str) -> str:
    r = client.get("/definitions", params={"typ": "AT_8_2_Analyse"})
    return next(d["id"] for d in r.json() if d["version"] == version)


def _set_status(client, definition_id: str, *, target: str, deactivate_id: str | None) -> None:
    """Test-only helper: directly toggles status via the DB layer."""
    from app.database import SessionLocal
    from app.models import FormDefinition

    with SessionLocal() as db:
        if deactivate_id:
            other = db.get(FormDefinition, deactivate_id)
            if other:
                other.status = "draft"  # so we can re-activate cleanly
        d = db.get(FormDefinition, definition_id)
        d.status = "draft"
        db.commit()
    client.post(f"/definitions/{definition_id}/activate")
