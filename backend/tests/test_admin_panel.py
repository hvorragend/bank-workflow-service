"""Smoke-Tests fuer die neuen Admin-Panel-Endpunkte (Phase 4).

Statt jeden Endpoint einzeln zu zerlegen, gehen wir die Hauptpfade durch:
- Permission-Katalog ist erreichbar
- Roles-CRUD funktioniert (mit Lockout-Schutz)
- User-CRUD funktioniert (mit Lockout-Schutz)
- LDAP/SMTP/Escalation Config GET/PUT
- System-Status meldet sinnvolle Werte
- Notfall-Login wird auditiert
"""
from __future__ import annotations

import pytest

from .conftest import auth_header, login_as


@pytest.fixture
def admin_headers(client):
    return auth_header(login_as(client, "admin"))


@pytest.fixture
def nobody_headers(client):
    return auth_header(login_as(client, "nobody"))


def test_permissions_catalog_returns_known_codes(client, admin_headers):
    r = client.get("/admin/permissions", headers=admin_headers)
    assert r.status_code == 200
    codes = {p["code"] for p in r.json()}
    expected = {
        "admin.users.read", "admin.users.write", "admin.roles.write",
        "admin.ldap.read", "admin.smtp.write", "admin.escalation.write",
        "admin.system.rekey", "admin.audit.read",
        "definitions.upload", "instances.create",
    }
    assert expected.issubset(codes), f"fehlende: {expected - codes}"


def test_roles_listing_includes_admin_and_defaults(client, admin_headers):
    r = client.get("/admin/roles", headers=admin_headers)
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    for n in ("Admin", "Vorstand", "Compliance", "Risikomanagement", "Bereichsleiter"):
        assert n in names


def test_admin_role_is_system_and_holds_all_permissions(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()
    admin = next(r for r in roles if r["name"] == "Admin")
    assert admin["is_system"] is True
    perms = client.get("/admin/permissions", headers=admin_headers).json()
    expected = {p["code"] for p in perms}
    assert expected.issubset(set(admin["permission_codes"]))


def test_role_cannot_be_deleted_if_in_use(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()
    vorstand = next(r for r in roles if r["name"] == "Vorstand")
    r = client.delete(f"/admin/roles/{vorstand['id']}", headers=admin_headers)
    assert r.status_code == 409


def test_role_create_update_delete_roundtrip(client, admin_headers):
    r = client.post("/admin/roles", json={
        "name": "TestRolle",
        "description": "Smoke",
        "permission_codes": ["instances.read"],
    }, headers=admin_headers)
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]

    # Update Permissions
    r = client.put(f"/admin/roles/{role_id}/permissions", json={
        "permission_codes": ["instances.read", "instances.create"],
    }, headers=admin_headers)
    assert r.status_code == 200
    assert set(r.json()["permission_codes"]) == {"instances.read", "instances.create"}

    # Delete
    r = client.delete(f"/admin/roles/{role_id}", headers=admin_headers)
    assert r.status_code == 204


def test_admin_role_cannot_be_deleted(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()
    admin = next(r for r in roles if r["name"] == "Admin")
    r = client.delete(f"/admin/roles/{admin['id']}", headers=admin_headers)
    assert r.status_code == 409


def test_user_create_with_role_and_login(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()
    vorstand_id = next(r["id"] for r in roles if r["name"] == "Vorstand")
    r = client.post("/admin/users", json={
        "username": "neu_vorstand",
        "display_name": "Neuer Vorstand",
        "email": "neu@test.local",
        "password": "neu-passwort-1",
        "role_ids": [vorstand_id],
    }, headers=admin_headers)
    assert r.status_code == 201, r.text

    token = login_as(client, "neu_vorstand", "neu-passwort-1")
    me = client.get("/auth/me", headers=auth_header(token)).json()
    assert "Vorstand" in me["roles"]
    assert "instances.decide" in me["permissions"]


def test_nobody_cannot_access_admin(client, nobody_headers):
    r = client.get("/admin/users", headers=nobody_headers)
    assert r.status_code == 403


def test_smtp_config_default_disabled(client, admin_headers):
    r = client.get("/admin/smtp", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["enabled"], bool)
    assert "password_set" in body


def test_smtp_password_round_trip_masked(client, admin_headers):
    """PUT speichert verschluesselt; GET liefert null + password_set=True."""
    r = client.put("/admin/smtp", json={
        "username": "test", "password": "supergeheim",
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["password_set"] is True

    r = client.put("/admin/smtp", json={"password": ""}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["password_set"] is False


def test_ldap_config_endpoints(client, admin_headers):
    r = client.get("/admin/ldap", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "server" in body and "bind_user_template" in body

    r = client.put("/admin/ldap", json={
        "server": "ldaps://ldap.test", "bind_user_template": "cn={username},dc=test",
    }, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["server"] == "ldaps://ldap.test"


def test_escalation_config_get_set_and_run_now(client, admin_headers):
    r = client.get("/admin/escalation", headers=admin_headers)
    assert r.status_code == 200

    r = client.put("/admin/escalation", json={
        "enabled": False, "default_sla_days": 7, "interval_minutes": 30,
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_sla_days"] == 7
    assert body["interval_minutes"] == 30

    r = client.post("/admin/escalation/run-now", headers=admin_headers)
    assert r.status_code == 200
    assert "counts" in r.json()


def test_auth_mode_get_set(client, admin_headers):
    r = client.get("/admin/auth-mode", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["mode"] in ("local", "ldap", "both")

    r = client.put("/admin/auth-mode", json={"mode": "both"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["mode"] == "both"

    # Wieder zurueck — sonst stoeren spaetere Tests evtl. den Local-Login.
    client.put("/admin/auth-mode", json={"mode": "local"}, headers=admin_headers)


def test_system_status_reports_expected_fields(client, admin_headers):
    r = client.get("/admin/system/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["db_ok"] is True
    assert body["user_count"] >= 1
    assert body["admin_count"] >= 1
    assert body["encryption_key_fingerprint"]


def test_emergency_login_only_active_when_no_db_admin(client):
    """Solange ein aktiver Admin in der DB existiert, wird die Notfall-Datei
    NICHT geladen — der Notfall-User hat keinen Zugang. Das schuetzt davor,
    dass eine versehentlich liegen gelassene Notfall-Datei einen alternativen
    Admin-Pfad oeffnet."""
    r = client.post("/auth/login", json={"username": "notfall", "password": "notfall-pw"})
    assert r.status_code == 401


def test_emergency_users_load_when_admin_missing(monkeypatch):
    """Direkt-Test des Bootstrap-Pfads: ohne aktiven Admin werden die
    Notfall-User aus der Datei in die In-Memory-Registry geladen."""
    from app import bootstrap, models
    from app.database import SessionLocal

    bootstrap.reset_emergency_users()
    with SessionLocal() as db:
        admins = list(db.scalars(__import__("sqlalchemy").select(models.User)).all())
        # User temporaer deaktivieren, damit kein aktiver Admin existiert
        for u in admins:
            u.is_active = False
        db.commit()
        try:
            bootstrap.ensure_emergency_admin_or_die(db)
            assert "notfall" in bootstrap.get_emergency_users()
        finally:
            for u in admins:
                u.is_active = True
            db.commit()
    bootstrap.reset_emergency_users()


def test_secrets_encryption_round_trip():
    from app.security.secrets import decrypt, encrypt
    token = encrypt("supergeheim")
    assert token and token != "supergeheim"
    assert decrypt(token) == "supergeheim"
    assert encrypt(None) is None
    assert decrypt(None) is None


def test_template_preview_substitutes_variables(client, admin_headers):
    r = client.post("/admin/notifications/templates/approved/preview", json={
        "subject": "[Test] $titel",
        "body": "Hallo $antragsteller, dein Antrag $titel wurde $status.",
        "context": {"titel": "Demo", "antragsteller": "alice", "status": "genehmigt"},
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["subject"] == "[Test] Demo"
    assert "alice" in out["body"] and "genehmigt" in out["body"]
