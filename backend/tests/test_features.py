"""Tests fuer die Quick-Win-Features N-003 (Audit-CSV-Export) und
N-004 (Kommentarpflicht bei Ablehnung/Zurueckweisung)."""
from __future__ import annotations

VALID_AT82 = {
    "antragsteller": {"name": "FB", "abteilung": "IT", "datum": "2026-05-05"},
    "vorhaben": {"titel": "Feature-Test", "kategorie": "IT-System"},
    "wesentlichkeitskriterien": {
        "ertragsrelevanz": "mittel", "risikorelevanz": "mittel",
        "aufsichtsrechtlicheRelevanz": True, "doraRelevanz": True,
    },
    "ergebnis": {
        "wesentlich": True,
        "begruendung": "Mindestens 50 Zeichen Begruendung mit ausreichend Inhalt fuer das Schema.",
    },
}


def _submit_at82(client, admin_auth) -> str:
    defs = client.get("/definitions", headers=admin_auth).json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    iid = client.post(
        "/instances", json={"form_definition_id": target["id"], "daten": VALID_AT82}, headers=admin_auth
    ).json()["id"]
    r = client.post(f"/instances/{iid}/submit", headers=admin_auth)
    assert r.status_code == 200, r.text
    return iid


# ---------- N-004: Kommentarpflicht ----------

def test_return_without_comment_is_rejected(client, admin_auth):
    iid = _submit_at82(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "fachbereich", "entscheidung": "returned"},
        headers=admin_auth,
    )
    assert r.status_code == 422, r.text
    assert "Begruendung" in r.json()["detail"]


def test_reject_without_comment_is_rejected(client, admin_auth):
    iid = _submit_at82(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "fachbereich", "entscheidung": "rejected", "kommentar": "   "},
        headers=admin_auth,
    )
    assert r.status_code == 422, r.text


def test_return_with_comment_succeeds(client, admin_auth):
    iid = _submit_at82(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "fachbereich", "entscheidung": "returned",
              "kommentar": "Bitte Abschnitt 2 nachschaerfen."},
        headers=admin_auth,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "entwurf"


def test_approve_without_comment_still_works(client, admin_auth):
    """Die Pflicht gilt nur fuer Ablehnung/Zurueckweisung, nicht fuer Genehmigung."""
    iid = _submit_at82(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "fachbereich", "entscheidung": "approved"},
        headers=admin_auth,
    )
    assert r.status_code == 200, r.text


# ---------- N-003: Audit-CSV-Export ----------

def test_audit_csv_export(client, admin_auth):
    # Etwas Audit-Aktivitaet erzeugen.
    _submit_at82(client, admin_auth)
    r = client.get("/admin/audit", params={"format": "csv"}, headers=admin_auth)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in r.headers.get("content-disposition", "")
    body = r.text
    assert body.splitlines()[0] == "id;zeitstempel;kategorie;action;akteur;target_type;target_id;ip;payload"


def test_audit_json_still_default(client, admin_auth):
    r = client.get("/admin/audit", headers=admin_auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
