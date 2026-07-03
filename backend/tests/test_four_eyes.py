"""N-007: 4-Augen-Prinzip pro Knoten (min_approvals).

Ein User-Task mit min_approvals=2 wird erst nach Zustimmung ZWEIER distinkter
Personen abgeschlossen; derselbe Nutzer kann nicht doppelt genehmigen.
"""
from __future__ import annotations

from .conftest import auth_header, login_as

GRAPH_4EYES = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "pruefung", "type": "user_task", "label": "Doppelpruefung",
         "rolle": "Vorstand", "min_approvals": 2},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "pruefung"},
        {"from": "pruefung", "to": "end"},
    ],
}
JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object", "required": ["titel"],
    "properties": {"titel": {"type": "string", "minLength": 1}},
}
UI_SCHEMA = {"type": "VerticalLayout", "elements": [
    {"type": "Control", "scope": "#/properties/titel"}]}


def _create_active_4eyes_def(client, admin_auth) -> str:
    payload = {
        "typ": "VierAugen_Test", "version": "1.0.0", "titel": "4-Augen-Test",
        "json_schema": JSON_SCHEMA, "ui_schema": UI_SCHEMA,
        "workflow_graph": GRAPH_4EYES, "erstellt_von": "admin",
    }
    r = client.post("/definitions", json=payload, headers=admin_auth)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = client.post(f"/definitions/{did}/activate", headers=admin_auth)
    assert r.status_code == 200, r.text
    return did


def _new_instance(client, admin_auth, did) -> str:
    r = client.post("/instances", json={"form_definition_id": did, "daten": {"titel": "X"}}, headers=admin_auth)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert client.post(f"/instances/{iid}/submit", headers=admin_auth).status_code == 200
    return iid


def _decide(client, auth, iid, decision):
    return client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "pruefung", "entscheidung": decision},
        headers=auth,
    )


def test_min_approvals_requires_two_distinct_approvers(client, admin_auth):
    did = _create_active_4eyes_def(client, admin_auth)
    iid = _new_instance(client, admin_auth, did)

    # 1. Genehmigung (admin, Rolle Vorstand): Knoten bleibt aktiv (1 von 2).
    assert _decide(client, admin_auth, iid, "approved").status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert state["status"] == "in_pruefung"
    assert {a["node_id"] for a in state["active_stages"]} == {"pruefung"}

    # Derselbe Nutzer darf NICHT ein zweites Mal genehmigen.
    r = _decide(client, admin_auth, iid, "approved")
    assert r.status_code == 409, r.text
    assert "bereits genehmigt" in r.json()["detail"]

    # 2. Genehmigung durch eine ANDERE Person mit Rolle Vorstand -> abgeschlossen.
    vorstand = auth_header(login_as(client, "vorstand"))
    assert _decide(client, vorstand, iid, "approved").status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert state["status"] == "genehmigt"
    assert state["active_stages"] == []


def test_min_approvals_zero_rejected_by_validator(client, admin_auth):
    bad = {
        "typ": "VierAugen_Bad", "version": "1.0.0", "titel": "Bad",
        "json_schema": JSON_SCHEMA, "ui_schema": UI_SCHEMA,
        "workflow_graph": {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "t", "type": "user_task", "rolle": "Vorstand", "min_approvals": 0},
                {"id": "end", "type": "end"},
            ],
            "edges": [{"from": "start", "to": "t"}, {"from": "t", "to": "end"}],
        },
        "erstellt_von": "admin",
    }
    r = client.post("/definitions", json=bad, headers=admin_auth)
    assert r.status_code == 422, r.text
    assert "min_approvals" in r.json()["detail"]
