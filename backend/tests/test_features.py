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


# ---------- N-005: Aging-Report ----------

def test_aging_report_lists_open_tasks_per_role(client, admin_auth):
    _submit_at82(client, admin_auth)  # aktiver Task in Rolle Fachbereichsleiter
    r = client.get("/instances/aging", headers=admin_auth)
    assert r.status_code == 200, r.text
    rows = r.json()
    fb = next((x for x in rows if x["rolle"] == "Fachbereichsleiter"), None)
    assert fb is not None
    assert fb["offene_tasks"] >= 1
    assert fb["alter_tage"] is not None


# ---------- N-001: Vertretung/Delegation ----------

def test_delegation_crud_and_self_service(client):
    from datetime import date, timedelta

    from .conftest import auth_header, login_as
    fb = auth_header(login_as(client, "fachbereich"))
    today = date.today().isoformat()
    ende = (date.today() + timedelta(days=7)).isoformat()

    # Anlegen
    r = client.post("/delegations", json={"to_username": "risiko", "von_datum": today, "bis_datum": ende}, headers=fb)
    assert r.status_code == 201, r.text
    did = r.json()["id"]

    # Eigene Liste enthaelt sie
    own = client.get("/delegations", headers=fb).json()
    assert any(d["id"] == did for d in own)

    # Selbstvertretung und falsche Datumsreihenfolge werden abgelehnt
    assert client.post("/delegations", json={"to_username": "fachbereich", "von_datum": today, "bis_datum": ende}, headers=fb).status_code == 400
    assert client.post("/delegations", json={"to_username": "risiko", "von_datum": ende, "bis_datum": today}, headers=fb).status_code == 400

    # Fremde Vertretung ist nicht loeschbar (404, kein Leak)
    risiko = auth_header(login_as(client, "risiko"))
    assert client.delete(f"/delegations/{did}", headers=risiko).status_code == 404

    # Eigene loeschbar
    assert client.delete(f"/delegations/{did}", headers=fb).status_code == 204


def test_active_deputy_receives_role_emails():
    """Waehrend der Vertretung ist die Mail des Vertreters bei der Rolle des
    Abwesenden mit dabei."""
    from datetime import date, timedelta

    from sqlalchemy import select

    from app import models
    from app.config_service.role_emails import emails_for_role
    from app.database import SessionLocal

    with SessionLocal() as db:
        deleg = models.Delegation(
            from_username="fachbereich", to_username="risiko",
            von_datum=date.today() - timedelta(days=1),
            bis_datum=date.today() + timedelta(days=1),
        )
        db.add(deleg)
        db.commit()
        try:
            emails = emails_for_role(db, "Fachbereichsleiter")
            assert "risiko@test.local" in emails
            assert "fachbereich@test.local" in emails
        finally:
            db.delete(deleg)
            db.commit()
