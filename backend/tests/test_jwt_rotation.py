"""JWT-Schluesselrotation: alter Token bleibt gueltig, solange das alte Secret
in JWT_SECRETS steht. Neue Tokens werden mit dem neuesten Secret signiert.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest


def _build_token(secret: str, *, sub: str = "admin", roles: list[str] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "name": f"Test {sub}",
        "email": f"{sub}@test.local",
        "roles": roles or ["Admin"],
        # /instances verlangt jetzt die Permission instances.read — der
        # Rotations-Test nutzt den Endpunkt nur als beliebige Auth-geschuetzte
        # Route, deshalb den noetigen Permission-Claim mitgeben.
        "permissions": ["instances.read"],
        "auth_source": "local",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "type": "access",
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def rotated_secrets(monkeypatch):
    """Setzt JWT_SECRETS auf 'neu,alt' und stellt das ursprungliche JWT_SECRET
    wieder her. Wir nutzen das alte JWT_SECRET als 'alten Key'."""
    altes = os.environ["JWT_SECRET"]
    neues = "neuer-secret-key-mit-mindestens-32-zeichen-laenge!!!"
    monkeypatch.setenv("JWT_SECRETS", f"{neues},{altes}")

    from app.auth.config import reset_settings_cache
    reset_settings_cache()
    yield {"alt": altes, "neu": neues}
    reset_settings_cache()


@pytest.mark.fachlich(
    anforderung="MaRisk AT 7.2 — JWT-Schluesselrotation",
    soll="Tokens, die mit dem alten Schluessel signiert wurden, bleiben gueltig, solange er in JWT_SECRETS steht.",
)
def test_token_signed_with_old_key_still_accepted(client, rotated_secrets):
    """Ein Token, der mit dem alten Secret signiert ist, muss vom Backend
    akzeptiert werden, solange JWT_SECRETS noch das alte Secret enthaelt."""
    altes_token = _build_token(rotated_secrets["alt"])
    r = client.get("/instances", headers={"Authorization": f"Bearer {altes_token}"})
    assert r.status_code == 200, r.text


def test_token_signed_with_unknown_key_rejected(client, rotated_secrets):
    """Ein Token mit fremdem Schluessel wird mit 401 abgewiesen."""
    fremder_key = "anderer-key-der-nicht-konfiguriert-ist!!!!!!!!!!"
    fremdes_token = _build_token(fremder_key)
    r = client.get("/instances", headers={"Authorization": f"Bearer {fremdes_token}"})
    assert r.status_code == 401


def test_new_logins_use_first_secret(client, rotated_secrets):
    """Neuer Login muss mit dem ersten Schluessel aus JWT_SECRETS signieren."""
    r = client.post("/auth/login", json={"username": "admin", "password": "test123!"})
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    # Verify: dekodiert nur mit dem neuen Schluessel sauber
    payload = pyjwt.decode(new_token, rotated_secrets["neu"], algorithms=["HS256"])
    assert payload["sub"] == "admin"

    # Mit altem Schluessel: Signatur passt nicht mehr
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(new_token, rotated_secrets["alt"], algorithms=["HS256"])
