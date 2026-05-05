"""Admin-Endpunkte: Workflow-Upload, Schema-Diff, Audit-Log (Commit 5)."""
from __future__ import annotations

import json

from .conftest import auth_header, login_as


def test_upload_creates_draft_definition(client, admin_auth):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Test-Maske",
        "type": "object",
        "required": ["titel"],
        "properties": {"titel": {"type": "string", "minLength": 5}},
    }
    ui = {
        "type": "VerticalLayout",
        "elements": [
            {"type": "Group", "label": "Allgemein",
             "elements": [{"type": "Control", "scope": "#/properties/titel"}]}
        ],
    }
    files = {
        "json_schema": ("schema.json", json.dumps(schema).encode(), "application/json"),
        "ui_schema":   ("ui.json",     json.dumps(ui).encode(),     "application/json"),
    }
    data = {
        "typ": "Test_Maske",
        "version": "1.0.0",
        "titel": "Test-Maske v1.0.0",
        "workflow_stages": json.dumps([{"name": "fb", "rolle": "Fachbereichsleiter"}]),
    }
    r = client.post("/admin/definitions/upload", data=data, files=files, headers=admin_auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["typ"] == "Test_Maske"
    assert body["version"] == "1.0.0"


def test_upload_rejects_invalid_json_schema(client, admin_auth):
    bad_schema = {"type": "not-a-real-type"}  # ungueltig nach Draft-2020-12
    files = {
        "json_schema": ("schema.json", json.dumps(bad_schema).encode(), "application/json"),
        "ui_schema":   ("ui.json",     b'{"type":"VerticalLayout","elements":[]}', "application/json"),
    }
    data = {
        "typ": "Bad", "version": "1.0.0", "titel": "Bad",
        "workflow_stages": json.dumps([{"name": "fb", "rolle": "Fachbereichsleiter"}]),
    }
    r = client.post("/admin/definitions/upload", data=data, files=files, headers=admin_auth)
    assert r.status_code == 422
    assert "Draft-2020-12" in r.json()["detail"]


def test_upload_blocks_non_admin(client):
    fb = login_as(client, "fachbereich")
    files = {
        "json_schema": ("schema.json", b'{"type":"object"}', "application/json"),
        "ui_schema":   ("ui.json",     b'{"type":"VerticalLayout","elements":[]}', "application/json"),
    }
    data = {
        "typ": "X", "version": "1.0.0", "titel": "X",
        "workflow_stages": json.dumps([{"name": "fb", "rolle": "Fachbereichsleiter"}]),
    }
    r = client.post("/admin/definitions/upload", data=data, files=files, headers=auth_header(fb))
    assert r.status_code == 403


def test_diff_between_at_8_2_versions(client, admin_auth):
    """v1 und v2 unterscheiden sich um doraRelevanz — Diff muss das zeigen."""
    defs = client.get("/definitions").json()
    v1 = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["version"] == "1.0.0")
    v2 = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["version"] == "2.0.0")
    r = client.get(f"/admin/definitions/{v1['id']}/diff/{v2['id']}", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    paths = [d["path"] for d in body["diffs"]]
    # doraRelevanz erscheint als field_added irgendwo unter wesentlichkeitskriterien
    assert any("doraRelevanz" in p for p in paths), paths
    # required hat sich geaendert (doraRelevanz ist in v2 Pflicht)
    assert any(d["kind"] == "field_added" and "doraRelevanz" in d["path"] for d in body["diffs"])


def test_audit_log_lists_login_events(client, admin_auth):
    # Provoziere einen Login, dann pruefe den Audit-Eintrag.
    login_as(client, "vorstand")
    r = client.get("/admin/audit?kategorie=auth", headers=admin_auth)
    assert r.status_code == 200
    events = r.json()
    assert len(events) > 0
    actions = {e["action"] for e in events}
    assert "login.success" in actions or any(a.startswith("login") for a in actions)


def test_retire_active_definition(client, admin_auth):
    """Eine eigens fuer den Test angelegte aktive Definition wird auf 'retired' gesetzt.

    Wir arbeiten bewusst auf einem isolierten Test-Schema, damit andere Tests
    weiter aktive Demo-Definitionen vorfinden.
    """
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}},
    }
    ui = {"type": "VerticalLayout",
          "elements": [{"type": "Group", "label": "G",
                        "elements": [{"type": "Control", "scope": "#/properties/a"}]}]}
    files = {
        "json_schema": ("s.json", json.dumps(schema).encode(), "application/json"),
        "ui_schema":   ("u.json", json.dumps(ui).encode(),     "application/json"),
    }
    data = {
        "typ": "Retire_Test", "version": "1.0.0", "titel": "Retire-Test",
        "workflow_stages": json.dumps([{"name": "fb", "rolle": "Fachbereichsleiter"}]),
    }
    r = client.post("/admin/definitions/upload", data=data, files=files, headers=admin_auth)
    assert r.status_code == 201, r.text
    d_id = r.json()["id"]

    r = client.post(f"/definitions/{d_id}/activate", headers=admin_auth)
    assert r.status_code == 200

    r = client.post(f"/admin/definitions/{d_id}/retire", headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["status"] == "retired"

    # Audit-Eintrag muss existieren
    r = client.get("/admin/audit?kategorie=definition", headers=admin_auth)
    actions = {e["action"] for e in r.json()}
    assert "definition.retired" in actions
