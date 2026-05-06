"""Regressionstest: Platzhalter aus deploy/.env.example werden mit klarer
Fehlermeldung abgefangen, statt mit kryptischem 'Incorrect padding'.

Hintergrund: Wer .env.example nach .env kopiert und 'CONFIG_ENCRYPTION_KEY=
replace-with-fernet-generate-key-output' nicht ersetzt, hatte in der Praxis
nur eine Fernet-Library-Meldung und einen Backend-Crash-Loop hinter nginx
(=> 502 fuer alle Requests, auch /auth/login). Der zusaetzliche Pre-Check
in app.security.secrets soll das verhindern.
"""
from __future__ import annotations

import pytest

from app.security import secrets as secrets_mod


@pytest.fixture
def reset_secrets_cache():
    secrets_mod.reset_cache()
    yield
    secrets_mod.reset_cache()


@pytest.mark.parametrize("placeholder", [
    "replace-with-fernet-generate-key-output",
    "replace-with-openssl-rand-hex-32",
    "replace-me",
    "replace-me-in-production",
    "changeme",
])
def test_placeholder_value_yields_explicit_error(monkeypatch, reset_secrets_cache, placeholder):
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", placeholder)
    monkeypatch.delenv("CONFIG_ENCRYPTION_KEY_OLD", raising=False)

    with pytest.raises(secrets_mod.EncryptionUnavailable) as excinfo:
        secrets_mod.assert_encryption_available()

    msg = str(excinfo.value)
    assert "Platzhalter" in msg
    assert ".env.example" in msg
    assert placeholder in msg


def test_valid_fernet_key_passes(monkeypatch, reset_secrets_cache):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.delenv("CONFIG_ENCRYPTION_KEY_OLD", raising=False)

    secrets_mod.assert_encryption_available()


def test_invalid_padding_still_yields_friendly_error(monkeypatch, reset_secrets_cache):
    """Wenn der Wert kein Platzhalter ist, aber trotzdem keinen Fernet-Key
    darstellt (haeufig: 'openssl rand -hex 32'-Output), bleibt es bei der
    bestehenden Hint-Message."""
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", "a" * 64)  # 64 Hex-Zeichen
    monkeypatch.delenv("CONFIG_ENCRYPTION_KEY_OLD", raising=False)

    with pytest.raises(secrets_mod.EncryptionUnavailable) as excinfo:
        secrets_mod.assert_encryption_available()

    msg = str(excinfo.value)
    assert "Fernet" in msg
    assert "Fernet.generate_key" in msg
