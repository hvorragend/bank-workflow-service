"""Symmetrische Verschluesselung sensibler Config-Werte (SMTP-Passwort,
LDAP-Service-Account-Passwort, optional CA-Cert).

Schluessel via Env-Var `CONFIG_ENCRYPTION_KEY` (Pflicht; 32 url-safe base64
Bytes — der Format, den `Fernet.generate_key()` zurueckgibt).
Fehlt der Schluessel, refused der App-Start (siehe bootstrap).

Schluessel-Rotation: optional `CONFIG_ENCRYPTION_KEY_OLD` als Decrypt-only-
Fallback. Nach erfolgreicher Re-Encryption (admin endpoint) kann der alte
Schluessel entfernt werden.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class EncryptionUnavailable(RuntimeError):
    """Wird beim App-Start geworfen, wenn der Schluessel fehlt oder ungueltig ist."""


_KEY_HOWTO = (
    "Generiere einen mit:\n"
    "    python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'\n"
    "und setze ihn als CONFIG_ENCRYPTION_KEY in der Umgebung."
)

# Werte, die in deploy/.env.example als Platzhalter stehen. Wenn jemand
# .env.example nach .env kopiert und nur einen Teil ersetzt, fangen wir das
# hier mit einer sehr deutlichen Meldung ab — sonst kommt nur ein generisches
# „Incorrect padding" aus cryptography zurueck und der Operator raetselt.
_PLACEHOLDER_VALUES = frozenset({
    "replace-with-fernet-generate-key-output",
    "replace-with-openssl-rand-hex-32",
    "replace-me",
    "replace-me-in-production",
    "changeme",
})


def _load_key(env_name: str) -> bytes | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    if raw in _PLACEHOLDER_VALUES:
        raise EncryptionUnavailable(
            f"{env_name} steht noch auf dem Platzhalter '{raw}' aus "
            "deploy/.env.example. Du hast die Beispieldatei kopiert, aber "
            "den Wert nicht ersetzt. " + _KEY_HOWTO
        )
    return raw.encode("ascii")


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    primary = _load_key("CONFIG_ENCRYPTION_KEY")
    if not primary:
        raise EncryptionUnavailable(
            "CONFIG_ENCRYPTION_KEY ist nicht gesetzt. " + _KEY_HOWTO
        )
    keys: list[Fernet] = []
    try:
        keys.append(Fernet(primary))
    except (ValueError, TypeError) as e:
        raise EncryptionUnavailable(
            f"CONFIG_ENCRYPTION_KEY ist kein gueltiger Fernet-Schluessel: {e}. " + _KEY_HOWTO
        ) from e
    old = _load_key("CONFIG_ENCRYPTION_KEY_OLD")
    if old:
        try:
            keys.append(Fernet(old))
        except (ValueError, TypeError) as e:
            raise EncryptionUnavailable(
                f"CONFIG_ENCRYPTION_KEY_OLD ist kein gueltiger Fernet-Schluessel: {e}."
            ) from e
    return MultiFernet(keys)


def reset_cache() -> None:
    """Fuer Tests: nach Aenderung der Env-Vars Cache leeren."""
    _fernet.cache_clear()


def assert_encryption_available() -> None:
    """Wird im App-Start aufgerufen — wirft EncryptionUnavailable, wenn kein
    gueltiger Schluessel vorhanden ist. So scheitert der Start frueh und mit
    klarer Fehlermeldung statt erst beim ersten Verschluesseln."""
    _fernet()


def encrypt(plaintext: str | None) -> str | None:
    """Verschluesselt mit dem aktuellen Schluessel. Gibt None bei None/empty zurueck."""
    if plaintext is None or plaintext == "":
        return None
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    """Entschluesselt; akzeptiert auch Tokens, die mit `CONFIG_ENCRYPTION_KEY_OLD`
    verschluesselt wurden (MultiFernet-Verhalten). Gibt None bei None/empty zurueck."""
    if ciphertext is None or ciphertext == "":
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        # Bewusst keine Klartext-Details zurueckgeben — dies ist meist ein
        # Hinweis auf fehlenden CONFIG_ENCRYPTION_KEY_OLD nach Rotation.
        raise EncryptionUnavailable(
            "Verschluesselter Wert konnte nicht entschluesselt werden. "
            "Falls Sie kuerzlich CONFIG_ENCRYPTION_KEY rotiert haben, setzen Sie "
            "den alten Schluessel als CONFIG_ENCRYPTION_KEY_OLD und fuehren Sie "
            "die Rekey-Aktion im Admin-Panel aus."
        ) from e


def key_fingerprint() -> str:
    """Kurzer, nicht-geheimer Fingerabdruck des aktuellen Schluessels —
    nuetzlich im /admin/system/status, damit Operatoren sehen koennen,
    welcher Schluessel aktiv ist, ohne ihn zu offenbaren."""
    primary = _load_key("CONFIG_ENCRYPTION_KEY") or b""
    if not primary:
        return ""
    import hashlib
    return hashlib.sha256(primary).hexdigest()[:12]
