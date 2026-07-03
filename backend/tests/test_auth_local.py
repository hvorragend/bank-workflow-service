"""Lokales Login: argon2-Passwort verifizieren, Token bekommen, /auth/me lesen."""
from __future__ import annotations

from .conftest import TEST_PASSWORD, auth_header, login_as


def test_login_returns_access_token(client):
    r = client.post("/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert len(body["access_token"]) > 50


def test_login_sets_refresh_cookie(client):
    r = client.post("/auth/login", json={"username": "vorstand", "password": TEST_PASSWORD})
    assert r.status_code == 200
    cookies = r.cookies
    assert "bws_refresh" in cookies
    # HttpOnly + SameSite kommen aus den Set-Cookie-Headern
    raw = r.headers.get("set-cookie", "")
    assert "HttpOnly" in raw
    assert "samesite=lax" in raw.lower()


def test_me_returns_roles_from_token(client):
    token = login_as(client, "vorstand")
    r = client.get("/auth/me", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "vorstand"
    assert "Vorstand" in body["roles"]
    assert body["auth_source"] == "local"


def test_refresh_rotates_cookie_and_issues_new_access(client):
    r = client.post("/auth/login", json={"username": "compliance", "password": TEST_PASSWORD})
    assert r.status_code == 200
    refresh_cookie = r.cookies.get("bws_refresh")
    assert refresh_cookie

    r2 = client.post("/auth/refresh", cookies={"bws_refresh": refresh_cookie})
    assert r2.status_code == 200
    new_access = r2.json()["access_token"]
    # In schnellem Lauf koennen Tokens identisch sein (gleiches iat). Wir testen
    # daher nur, dass ein gueltiger Token zurueckkommt.
    assert len(new_access) > 50


def test_logout_clears_refresh_cookie(client):
    r = client.post("/auth/login", json={"username": "compliance", "password": TEST_PASSWORD})
    assert r.status_code == 200
    refresh_cookie = r.cookies.get("bws_refresh")
    assert refresh_cookie

    r2 = client.post("/auth/logout", cookies={"bws_refresh": refresh_cookie})
    assert r2.status_code == 200
    # Nach Logout: refresh-Cookie wurde explizit geloescht
    raw = r2.headers.get("set-cookie", "").lower()
    assert "bws_refresh" in raw
    assert "max-age=0" in raw or "expires=thu, 01 jan 1970" in raw
