"""End-to-End-Smoke-Test fuer die Versions-Garantie.

- v1-Antrag erstellen (3 Wesentlichkeitskriterien).
- v2 aktivieren (4. Pflichtfeld doraRelevanz).
- Alter v1-Antrag bleibt gegen sein gepinntes v1-Schema gueltig.
- Neuer Antrag gegen v2 verlangt doraRelevanz.

Mit Commit 2 sind die Endpunkte auth-pflichtig — der admin_auth-Fixture liefert
einen Token mit allen Rollen.
"""
from __future__ import annotations

import pytest


VALID_V1_DATA = {
    "antragsteller": {
        "name": "Carsten Volmer",
        "abteilung": "IT-Sicherheit",
        "datum": "2026-05-05",
    },
    "vorhaben": {
        "titel": "Einfuehrung neuer Cloud-Storage",
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
            "und unterliegt erhoehten aufsichtsrechtlichen Anforderungen."
        ),
    },
}


def test_seeded_definitions_present(client):
    # GET /definitions ist oeffentlich lesbar — kein Token noetig.
    r = client.get("/definitions", params={"typ": "AT_8_2_Analyse"})
    assert r.status_code == 200
    versions = {d["version"]: d["status"] for d in r.json()}
    assert versions == {"1.0.0": "retired", "2.0.0": "active"}


@pytest.mark.fachlich(
    anforderung="MaRisk AT 7.2 Tz. 2 — Validierung gegen gepinnte Schema-Version",
    soll="Antrag gegen v2 ohne doraRelevanz wird mit 422 abgewiesen.",
)
def test_create_instance_against_active_v2_requires_dora(client, admin_auth):
    v2_id = _find_definition(client, "2.0.0")
    r = client.post(
        "/instances",
        json={"form_definition_id": v2_id, "daten": VALID_V1_DATA},
        headers=admin_auth,
    )
    assert r.status_code == 422
    assert "doraRelevanz" in r.json()["detail"]


@pytest.mark.fachlich(
    anforderung="MaRisk AT 7.2 Tz. 1 — Schemaversionsbindung",
    soll="Altantrag (v1) bleibt nach Maskenwechsel auf v2 gegen sein urspruengliches Schema renderbar.",
)
def test_old_v1_instance_stays_valid_after_v2_activation(client, admin_auth):
    """Der Kerntest: ein v1-Antrag bleibt nutzbar, auch wenn v2 inzwischen aktiv ist."""
    v1_id = _find_definition(client, "1.0.0")
    v2_id = _find_definition(client, "2.0.0")
    _set_status(client, admin_auth, v1_id, deactivate_id=v2_id)

    r = client.post(
        "/instances",
        json={"form_definition_id": v1_id, "daten": VALID_V1_DATA},
        headers=admin_auth,
    )
    assert r.status_code == 201, r.text
    instance_id = r.json()["id"]

    _set_status(client, admin_auth, v2_id, deactivate_id=v1_id)

    r = client.get(f"/instances/{instance_id}", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "AT_8_2_Analyse/1.0.0"
    krit = body["json_schema"]["properties"]["wesentlichkeitskriterien"]["properties"]
    assert "doraRelevanz" not in krit


@pytest.mark.fachlich(
    anforderung="MaRisk AT 4.3.1 — mehrstufige Genehmigung mit Rollentrennung",
    soll="Vollstaendige Approval-Kette laeuft durch alle drei Stages und endet mit status=genehmigt + 3 Audit-Eintraegen.",
)
def test_full_approval_chain(client, admin_auth):
    v2_id = _find_definition(client, "2.0.0")
    daten = {**VALID_V1_DATA}
    daten["wesentlichkeitskriterien"] = {
        **daten["wesentlichkeitskriterien"],
        "doraRelevanz": True,
    }

    r = client.post(
        "/instances",
        json={"form_definition_id": v2_id, "daten": daten},
        headers=admin_auth,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    assert client.post(
        f"/instances/{iid}/submit", headers=admin_auth
    ).json()["aktuelle_stage"] == "fachbereich"

    # Admin hat alle Rollen — kann durch alle Stages durch genehmigen.
    for stage_name in ["fachbereich", "risikomgmt", "vorstand"]:
        r = client.post(
            f"/instances/{iid}/decide",
            json={"entscheidung": "approved", "kommentar": f"OK in {stage_name}"},
            headers=admin_auth,
        )
        assert r.status_code == 200, r.text

    final = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert final["status"] == "genehmigt"
    assert len(final["approvals"]) == 3
    assert all(a["entscheidung"] == "approved" for a in final["approvals"])


# --- helpers ---

def _find_definition(client, version: str) -> str:
    r = client.get("/definitions", params={"typ": "AT_8_2_Analyse"})
    return next(d["id"] for d in r.json() if d["version"] == version)


def _set_status(client, admin_auth, definition_id: str, *, deactivate_id: str | None) -> None:
    """Test-Hilfsfunktion: setzt eine Definition auf 'active' und deaktiviert eine andere."""
    from app.database import SessionLocal
    from app.models import FormDefinition

    with SessionLocal() as db:
        if deactivate_id:
            other = db.get(FormDefinition, deactivate_id)
            if other:
                other.status = "draft"
        d = db.get(FormDefinition, definition_id)
        d.status = "draft"
        db.commit()
    r = client.post(f"/definitions/{definition_id}/activate", headers=admin_auth)
    assert r.status_code == 200, r.text
