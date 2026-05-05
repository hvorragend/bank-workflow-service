"""Datei-Anhaenge an FormInstances (Commit 6)."""
from __future__ import annotations

import io

import pytest


def _create_draft_instance(client, admin_auth) -> str:
    defs = client.get("/definitions").json()
    target = next(d for d in defs if d["status"] == "active" and d["typ"] == "AT_8_2_Analyse")
    daten = {
        "antragsteller": {"name": "T", "abteilung": "Test", "datum": "2026-05-05"},
        "vorhaben": {"titel": "Anhang-Testfall", "kategorie": "IT-System"},
        "wesentlichkeitskriterien": {
            "ertragsrelevanz": "mittel", "risikorelevanz": "mittel",
            "aufsichtsrechtlicheRelevanz": True, "doraRelevanz": False,
        },
        "ergebnis": {
            "wesentlich": False,
            "begruendung": "Hinreichend langer Begruendungstext, der das Mindestlimit ueberschreitet.",
        },
    }
    r = client.post("/instances", json={"form_definition_id": target["id"], "daten": daten}, headers=admin_auth)
    assert r.status_code == 201
    return r.json()["id"]


def _pdf_bytes() -> bytes:
    """Minimaler PDF-Header — fuer Tests reicht das fuer die Whitelist-Pruefung."""
    return b"%PDF-1.4\n%TestPDF\n" + b"x" * 100


@pytest.mark.fachlich(
    anforderung="MaRisk AT 7.2 — Datenintegritaet bei Dateianhaengen",
    soll="Hochgeladenes PDF wird mit SHA-256-Hash und Metadaten persistiert, byte-identisch wieder ausgeliefert.",
)
def test_upload_pdf_persists_metadata_and_hash(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    files = {"file": ("beschluss.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    r = client.post(f"/instances/{iid}/attachments", files=files, headers=admin_auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "beschluss.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] > 0
    assert len(body["sha256"]) == 64
    assert body["uploaded_by"] == "admin"


def test_upload_rejects_disallowed_extension(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    files = {"file": ("malicious.exe", io.BytesIO(b"MZ\x00\x00"), "application/octet-stream")}
    r = client.post(f"/instances/{iid}/attachments", files=files, headers=admin_auth)
    assert r.status_code == 415
    assert "nicht erlaubt" in r.json()["detail"].lower()


def test_upload_rejects_oversize(client, admin_auth, monkeypatch):
    """Wir setzen das Limit per Monkeypatch auf 100 Byte und schicken 200 Byte."""
    from app.routers import attachments as att_module
    monkeypatch.setattr(att_module, "MAX_BYTES", 100)
    iid = _create_draft_instance(client, admin_auth)
    files = {"file": ("big.pdf", io.BytesIO(b"%PDF-1.4\n" + b"x" * 200), "application/pdf")}
    r = client.post(f"/instances/{iid}/attachments", files=files, headers=admin_auth)
    assert r.status_code == 413


def test_list_and_download(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    files = {"file": ("anhang.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    r = client.post(f"/instances/{iid}/attachments", files=files, headers=admin_auth)
    att_id = r.json()["id"]

    # Liste
    r = client.get(f"/instances/{iid}/attachments", headers=admin_auth)
    assert r.status_code == 200
    assert any(a["id"] == att_id for a in r.json())

    # Download — Inhalt muss byte-identisch zurueckkommen
    r = client.get(f"/instances/{iid}/attachments/{att_id}", headers=admin_auth)
    assert r.status_code == 200
    assert r.content == _pdf_bytes()
    assert r.headers["content-type"].startswith("application/pdf")
    assert "filename" in r.headers["content-disposition"]


def test_delete_only_in_draft(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/attachments",
        files={"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=admin_auth,
    )
    att_id = r.json()["id"]

    # Im Entwurf darf geloescht werden
    r = client.delete(f"/instances/{iid}/attachments/{att_id}", headers=admin_auth)
    assert r.status_code == 204

    # Anhang ist weg
    r = client.get(f"/instances/{iid}/attachments", headers=admin_auth)
    assert all(a["id"] != att_id for a in r.json())


def test_delete_blocked_after_submit(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    r = client.post(
        f"/instances/{iid}/attachments",
        files={"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=admin_auth,
    )
    att_id = r.json()["id"]

    # Antrag einreichen — Stage in_pruefung
    client.post(f"/instances/{iid}/submit", headers=admin_auth)

    r = client.delete(f"/instances/{iid}/attachments/{att_id}", headers=admin_auth)
    assert r.status_code == 409


@pytest.mark.fachlich(
    anforderung="MaRisk AT 4.3.4 — revisionssichere Audit-Spur",
    soll="Datei-Upload erzeugt einen audit_events-Eintrag mit Action 'attachment.uploaded'.",
)
def test_audit_log_records_attachment_actions(client, admin_auth):
    iid = _create_draft_instance(client, admin_auth)
    client.post(
        f"/instances/{iid}/attachments",
        files={"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=admin_auth,
    )
    r = client.get("/admin/audit?kategorie=instance", headers=admin_auth)
    actions = {e["action"] for e in r.json()}
    assert "attachment.uploaded" in actions
