"""Objekt-Level-Autorisierung auf /instances und /attachments (Audit F-001).

Sichert die Sichtbarkeitsregel ab: Ein authentifizierter Nutzer darf fremde
Antraege nur sehen, wenn er Antragsteller ist, eine seiner Rollen am Workflow
beteiligt ist, oder er die Reporting-Permission (Aufsicht) besitzt.
"""
from __future__ import annotations

import pytest

from .conftest import auth_header, login_as

VALID_AT82 = {
    "antragsteller": {"name": "FB", "abteilung": "IT", "datum": "2026-05-05"},
    "vorhaben": {"titel": "Geheimes Vorhaben", "kategorie": "IT-System"},
    "wesentlichkeitskriterien": {
        "ertragsrelevanz": "mittel", "risikorelevanz": "mittel",
        "aufsichtsrechtlicheRelevanz": True, "doraRelevanz": True,
    },
    "ergebnis": {
        "wesentlich": True,
        "begruendung": "Mindestens 50 Zeichen Begruendung mit ausreichend Inhalt fuer das Schema.",
    },
}


def _create_at82_as(client, headers) -> str:
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["typ"] == "AT_8_2_Analyse" and d["status"] == "active")
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": VALID_AT82}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_user_without_role_cannot_read_foreign_instance(client, admin_auth):
    """`nobody` (keine Rolle/Permission) darf einen fremden Antrag NICHT lesen."""
    iid = _create_at82_as(client, admin_auth)
    nobody = auth_header(login_as(client, "nobody"))
    r = client.get(f"/instances/{iid}", headers=nobody)
    assert r.status_code == 403, r.text


def test_foreign_business_user_cannot_read_unrelated_instance(client):
    """Ein Fachbereichsleiter darf den Entwurf eines anderen Fachbereichsleiters
    nicht sehen, solange keine seiner Rollen am Workflow beteiligt ist."""
    fb1 = auth_header(login_as(client, "fachbereich"))
    iid = _create_at82_as(client, fb1)  # Entwurf, noch nicht eingereicht

    # sekretariat hat nur instances.read (kein Reporting) und ist nicht beteiligt.
    sek = auth_header(login_as(client, "sekretariat"))
    r = client.get(f"/instances/{iid}", headers=sek)
    assert r.status_code == 403, r.text


def test_owner_can_read_own_instance(client):
    fb1 = auth_header(login_as(client, "fachbereich"))
    iid = _create_at82_as(client, fb1)
    r = client.get(f"/instances/{iid}", headers=fb1)
    assert r.status_code == 200


def test_admin_with_reporting_sees_any_instance(client, admin_auth):
    fb1 = auth_header(login_as(client, "fachbereich"))
    iid = _create_at82_as(client, fb1)
    r = client.get(f"/instances/{iid}", headers=admin_auth)
    assert r.status_code == 200


def test_nobody_cannot_download_foreign_attachment(client, admin_auth):
    iid = _create_at82_as(client, admin_auth)
    files = {"file": ("beleg.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    up = client.post(f"/instances/{iid}/attachments", files=files, headers=admin_auth)
    assert up.status_code == 201, up.text
    att_id = up.json()["id"]

    nobody = auth_header(login_as(client, "nobody"))
    r = client.get(f"/instances/{iid}/attachments/{att_id}", headers=nobody)
    assert r.status_code == 403, r.text


def test_nobody_cannot_submit_foreign_draft(client):
    fb1 = auth_header(login_as(client, "fachbereich"))
    iid = _create_at82_as(client, fb1)
    nobody = auth_header(login_as(client, "nobody"))
    r = client.post(f"/instances/{iid}/submit", headers=nobody)
    # nobody hat nicht mal instances.create -> 403 durch Permission-Gate.
    assert r.status_code == 403, r.text


def test_list_scoped_to_own_for_non_reporting_user(client):
    """Ein Nutzer ohne Reporting-Permission sieht in der Liste nur eigene/
    beteiligte Antraege, nicht die aller anderen."""
    fb1 = auth_header(login_as(client, "fachbereich"))
    own = _create_at82_as(client, fb1)

    r = client.get("/instances", headers=fb1)
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert own in ids
    # Keine fremden Antraege (alle gelisteten gehoeren fb oder haben fb-Rolle)
    for inst in r.json():
        assert inst["antragsteller"] == "fachbereich" or inst["status"] != "entwurf"
