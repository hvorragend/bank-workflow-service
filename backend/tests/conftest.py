"""Test-Konfiguration: ephemere DB, Test-Users, Login-Helper.

Setzt fuer alle Tests:
- DATABASE_URL auf eine SQLite-Tempdatei (sauber pro Testlauf)
- JWT_SECRET auf einen festen Test-Wert
- AUTH_MODE auf 'local'
- USERS_CONFIG_PATH auf eine generierte Test-JSON mit allen Rollen, die die
  Workflow-Engine erwartet (Fachbereichsleiter, Risikomanagement, Vorstand,
  Bereichsleiter, Compliance, Vorstandssekretariat, Admin)

So koennen Tests sich per /auth/login einen Token holen und dann genauso
gegen die API arbeiten wie ein echter Frontend-Client.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

# --- Test-User -----------------------------------------------------------------

# Ein User pro Rolle, plus ein Multi-Rolle-Admin. Passwort ueberall "test123!".
TEST_PASSWORD = "test123!"

TEST_USERS = [
    ("admin",       ["Admin", "Vorstand", "Compliance", "Risikomanagement",
                     "Fachbereichsleiter", "Bereichsleiter", "Vorstandssekretariat"]),
    ("fachbereich", ["Fachbereichsleiter"]),
    ("risiko",      ["Risikomanagement"]),
    ("vorstand",    ["Vorstand"]),
    ("compliance",  ["Compliance"]),
    ("bereich",     ["Bereichsleiter"]),
    ("sekretariat", ["Vorstandssekretariat"]),
    ("nobody",      []),  # User ohne Rollen — fuer 403-Tests
]


@pytest.fixture(scope="session", autouse=True)
def _test_environment(tmp_path_factory):
    """Setzt Env-Vars + schreibt eine Test-users.json. Wird automatisch aktiv."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="bws_test_")
    os.close(db_fd)

    users_path = tmp_path_factory.mktemp("auth-config") / "users.json"
    hasher = PasswordHasher()
    users_payload = {
        "users": [
            {
                "username": uname,
                "password_argon2": hasher.hash(TEST_PASSWORD),
                "name": f"Test {uname}",
                "email": f"{uname}@test.local",
                "roles": roles,
            }
            for uname, roles in TEST_USERS
        ]
    }
    users_path.write_text(json.dumps(users_payload), encoding="utf-8")

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    # 32+ Bytes, sonst meckert PyJWT fuer HS256
    os.environ["JWT_SECRET"] = "test-secret-not-for-production-this-is-long-enough-32b"
    os.environ["AUTH_MODE"] = "local"
    os.environ["USERS_CONFIG_PATH"] = str(users_path)

    # Storage-Verzeichnis fuer Datei-Anhaenge (Phase 2 / Commit 6)
    storage_root = tmp_path_factory.mktemp("attachments")
    os.environ["STORAGE_BACKEND"] = "filesystem"
    os.environ["STORAGE_ROOT"] = str(storage_root)

    # Caches leeren, damit unsere Env-Vars greifen
    from app.auth.config import reset_settings_cache
    from app.storage import reset_storage_cache
    reset_settings_cache()
    reset_storage_cache()

    yield

    # Aufraeumen
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    """Importiert die App NACH der Env-Vorbereitung. Deaktiviert den Login-Rate-Limiter,
    damit Tests viele Logins schnell hintereinander machen koennen."""
    from app.auth.rate_limit import limiter
    from app.main import app

    limiter.enabled = False
    try:
        with TestClient(app) as c:
            yield c
    finally:
        limiter.enabled = True


# --- Login-Helper --------------------------------------------------------------

def login_as(client: TestClient, username: str, password: str = TEST_PASSWORD) -> str:
    """Loggt einen Test-User ein und gibt den Access-Token zurueck."""
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"Login fehlgeschlagen fuer {username}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token(client) -> str:
    """Ein einsatzbereiter Token mit allen Rollen — fuer Tests, die durch alle Stages laufen."""
    return login_as(client, "admin")


@pytest.fixture(scope="module")
def admin_auth(admin_token) -> dict[str, str]:
    return auth_header(admin_token)
