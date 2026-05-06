"""Test-Konfiguration: ephemere DB, Test-Users, Login-Helper.

Setzt fuer alle Tests:
- DATABASE_URL auf eine SQLite-Tempdatei (sauber pro Testlauf)
- JWT_SECRET auf einen festen Test-Wert
- CONFIG_ENCRYPTION_KEY auf einen festen Test-Wert
- USERS_CONFIG_PATH auf eine generierte Test-JSON mit allen Rollen — der
  Bootstrap importiert diese Datei beim ersten Start in die users-Tabelle.
- EMERGENCY_USERS_PATH auf einen einzelnen Notfall-Admin (damit
  ensure_emergency_admin_or_die in jedem Fall durchlaeuft).

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
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# --- Test-User -----------------------------------------------------------------

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
    ("nobody",      []),
]


@pytest.fixture(scope="session", autouse=True)
def _test_environment(tmp_path_factory):
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="bws_test_")
    os.close(db_fd)

    cfg_dir = tmp_path_factory.mktemp("auth-config")
    users_path = cfg_dir / "users.json"
    emergency_path = cfg_dir / "emergency_users.json"
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

    # Notfall-Admin: separater User, andere Credentials.
    emergency_payload = {
        "users": [
            {
                "username": "notfall",
                "password_argon2": hasher.hash("notfall-pw"),
                "name": "Notfall-Admin",
                "email": "notfall@test.local",
                "roles": ["Admin"],
            }
        ]
    }
    emergency_path.write_text(json.dumps(emergency_payload), encoding="utf-8")

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret-not-for-production-this-is-long-enough-32b"
    os.environ["CONFIG_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
    os.environ["USERS_CONFIG_PATH"] = str(users_path)
    os.environ["EMERGENCY_USERS_PATH"] = str(emergency_path)

    storage_root = tmp_path_factory.mktemp("attachments")
    os.environ["STORAGE_BACKEND"] = "filesystem"
    os.environ["STORAGE_ROOT"] = str(storage_root)

    from app.auth.config import reset_settings_cache
    from app.security import secrets as secrets_mod
    from app.storage import reset_storage_cache
    reset_settings_cache()
    secrets_mod.reset_cache()
    reset_storage_cache()

    yield

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    """Importiert die App NACH der Env-Vorbereitung. Deaktiviert den Login-Rate-Limiter."""
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
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"Login fehlgeschlagen fuer {username}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def approve_one(client: TestClient, headers: dict, instance_id: str, *, kommentar: str | None = None):
    """Genehmigt den genau einen aktiven Task einer Instance. Fuer lineare
    Workflows ohne parallele Branches die einfachste Form."""
    state = client.get(f"/instances/{instance_id}", headers=headers).json()
    actives = state.get("active_stages", [])
    assert len(actives) == 1, f"Erwartet exakt 1 aktiver Task, gefunden {len(actives)}: {actives}"
    body = {"node_id": actives[0]["node_id"], "entscheidung": "approved"}
    if kommentar is not None:
        body["kommentar"] = kommentar
    return client.post(f"/instances/{instance_id}/decide", json=body, headers=headers)


def approve_all_active(client: TestClient, headers: dict, instance_id: str, *, kommentar: str | None = None):
    """Genehmigt alle gerade aktiven Tasks. Sinnvoll bei parallelen Branches:
    eine Schleife aktiviert alle Branches eines Splits zugleich."""
    state = client.get(f"/instances/{instance_id}", headers=headers).json()
    for active in list(state.get("active_stages", [])):
        body = {"node_id": active["node_id"], "entscheidung": "approved"}
        if kommentar is not None:
            body["kommentar"] = kommentar
        client.post(f"/instances/{instance_id}/decide", json=body, headers=headers)


def reject_one(client: TestClient, headers: dict, instance_id: str, *, kommentar: str | None = None):
    state = client.get(f"/instances/{instance_id}", headers=headers).json()
    actives = state.get("active_stages", [])
    assert len(actives) >= 1, "Mind. 1 aktiver Task erforderlich, um abzulehnen."
    body = {"node_id": actives[0]["node_id"], "entscheidung": "rejected"}
    if kommentar is not None:
        body["kommentar"] = kommentar
    return client.post(f"/instances/{instance_id}/decide", json=body, headers=headers)


@pytest.fixture(scope="module")
def admin_token(client) -> str:
    return login_as(client, "admin")


@pytest.fixture(scope="module")
def admin_auth(admin_token) -> dict[str, str]:
    return auth_header(admin_token)


# --- MaRisk-Nachweismatrix-Generator ------------------------------------------

_REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "testdokumentation" / "nachweismatrix.md"


def pytest_addoption(parser):
    parser.addoption(
        "--marisk-report",
        action="store_true",
        default=False,
        help="Schreibt nach dem Lauf docs/testdokumentation/nachweismatrix.md.",
    )


_test_outcomes: list[dict] = []


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    keywords = report.keywords
    relevant = {"fachlich", "notfall", "performance"}.intersection(keywords)
    if not relevant:
        return
    _test_outcomes.append({
        "nodeid": report.nodeid,
        "outcome": report.outcome,
        "duration": round(report.duration, 3),
        "markers": sorted(relevant),
    })


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not config.getoption("--marisk-report"):
        return
    items_by_id = {it.nodeid: it for it in terminalreporter._session.items}
    rows: list[dict] = []
    for outc in _test_outcomes:
        item = items_by_id.get(outc["nodeid"])
        if not item:
            continue
        for marker in item.iter_markers():
            if marker.name not in {"fachlich", "notfall", "performance"}:
                continue
            rows.append({
                "marker": marker.name,
                "anforderung": marker.kwargs.get("anforderung")
                              or marker.kwargs.get("szenario")
                              or marker.kwargs.get("sla_ms"),
                "soll": marker.kwargs.get("soll"),
                "test": outc["nodeid"],
                "outcome": outc["outcome"],
                "duration": outc["duration"],
            })

    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Nachweismatrix",
        "",
        "> **Hinweis:** generiert vom Pytest-Hook `--marisk-report`.",
        f"> Letzter Lauf: `{exitstatus_to_text(exitstatus)}` mit {len(rows)} relevanten Test-Markern.",
        "",
        "## Fachliche Tests (MaRisk-/DORA-Bezug)",
        "",
        "| Anforderung | Soll-Verhalten | Test | Ergebnis | Dauer |",
        "|---|---|---|---|---|",
    ]
    for r in [r for r in rows if r["marker"] == "fachlich"]:
        lines.append(
            f"| {r['anforderung'] or '—'} | {r['soll'] or '—'} | `{r['test']}` | "
            f"{_outcome_emoji(r['outcome'])} {r['outcome']} | {r['duration']}s |"
        )
    lines += [
        "",
        "## Notfallszenarien",
        "",
        "| Szenario | Test | Ergebnis | Dauer |",
        "|---|---|---|---|",
    ]
    for r in [r for r in rows if r["marker"] == "notfall"]:
        lines.append(
            f"| {r['anforderung'] or '—'} | `{r['test']}` | "
            f"{_outcome_emoji(r['outcome'])} {r['outcome']} | {r['duration']}s |"
        )
    lines += [
        "",
        "## Performance-Tests",
        "",
        "| SLA (ms) | Test | Ergebnis | Dauer |",
        "|---|---|---|---|",
    ]
    for r in [r for r in rows if r["marker"] == "performance"]:
        lines.append(
            f"| {r['anforderung'] or '—'} | `{r['test']}` | "
            f"{_outcome_emoji(r['outcome'])} {r['outcome']} | {r['duration']}s |"
        )

    _REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    terminalreporter.write_line("")
    terminalreporter.write_line(f"MaRisk-Report geschrieben: {_REPORT_PATH}", green=True)


def exitstatus_to_text(code: int) -> str:
    return {0: "alle Tests gruen", 1: "Tests mit Fehlern", 2: "Aufruf-Fehler"}.get(code, f"exitcode={code}")


def _outcome_emoji(outcome: str) -> str:
    return {"passed": "OK", "failed": "FAIL", "skipped": "SKIP"}.get(outcome, outcome)
