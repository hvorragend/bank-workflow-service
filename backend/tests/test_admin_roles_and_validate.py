"""Tests fuer die neuen Admin-Endpunkte: /admin/roles + /admin/definitions/validate-graph."""
from __future__ import annotations

from .conftest import auth_header, login_as


def test_list_roles_returns_known_roles(client, admin_auth):
    r = client.get("/admin/roles", headers=admin_auth)
    assert r.status_code == 200
    roles = r.json()  # /admin/roles liefert seit dem Admin-Panel-Refactor RoleOut[]
    assert isinstance(roles, list)
    names = {r["name"] for r in roles}
    for needed in {"Admin", "Vorstand", "Compliance", "Fachbereichsleiter", "Risikomanagement", "Bereichsleiter"}:
        assert needed in names, names


def test_list_roles_blocks_non_admin(client):
    fb = login_as(client, "fachbereich")
    r = client.get("/admin/roles", headers=auth_header(fb))
    assert r.status_code == 403


def test_validate_graph_dryrun_accepts_valid_graph(client, admin_auth):
    g = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "t", "type": "user_task", "label": "x", "rolle": "Fachbereichsleiter"},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "t"}, {"from": "t", "to": "end"}],
    }
    r = client.post("/admin/definitions/validate-graph",
                    json={"workflow_graph": g}, headers=admin_auth)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_validate_graph_dryrun_rejects_cycle(client, admin_auth):
    g = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "a", "type": "user_task", "label": "a", "rolle": "Fachbereichsleiter"},
            {"id": "b", "type": "user_task", "label": "b", "rolle": "Risikomanagement"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "a"},
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},
            {"from": "b", "to": "end"},
        ],
    }
    r = client.post("/admin/definitions/validate-graph",
                    json={"workflow_graph": g}, headers=admin_auth)
    assert r.status_code == 422
    assert "Zyklus" in r.json()["detail"]


def test_validate_graph_dryrun_rejects_unknown_role(client, admin_auth):
    g = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "t", "type": "user_task", "label": "x", "rolle": "Astrologe"},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "t"}, {"from": "t", "to": "end"}],
    }
    r = client.post("/admin/definitions/validate-graph",
                    json={"workflow_graph": g}, headers=admin_auth)
    assert r.status_code == 422
    assert "Astrologe" in r.json()["detail"]


def test_upload_definition_with_workflow_graph(client, admin_auth):
    """Der bestehende /admin/definitions/upload akzeptiert jetzt workflow_graph
    statt workflow_stages — End-to-End-Test."""
    import json
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "required": ["a"], "properties": {"a": {"type": "string"}},
    }
    ui = {"type": "VerticalLayout", "elements": []}
    graph = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "t", "type": "user_task", "label": "x", "rolle": "Fachbereichsleiter"},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "t"}, {"from": "t", "to": "end"}],
    }
    files = {
        "json_schema": ("s.json", json.dumps(schema).encode(), "application/json"),
        "ui_schema":   ("u.json", json.dumps(ui).encode(),     "application/json"),
    }
    data = {
        "typ": "Graph_Upload_Test", "version": "1.0.0", "titel": "Graph-Upload-Test",
        "workflow_graph": json.dumps(graph),
    }
    r = client.post("/admin/definitions/upload", data=data, files=files, headers=admin_auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow_graph"]["nodes"][1]["id"] == "t"
