"""Auth-Konfiguration aus Env-Vars.

Seit dem Admin-Panel kommen Auth-Modus, lokale User und LDAP-Config nicht
mehr aus Dateien, sondern aus der DB (siehe app/config_service/). Hier
bleiben nur die echten Bootstrap-Werte: JWT-Secret(s), Cookie-Verhalten,
Token-Lifetimes.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Laufzeit-Konfiguration aus Env-Vars."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # JWT-Schluessel. Pflicht; im Test wird er ueber conftest gesetzt.
    # Schluesselrotation: JWT_SECRETS kann eine komma-separierte Liste enthalten —
    # das erste Element wird zum Signieren verwendet, alle anderen werden beim
    # Verify ebenfalls akzeptiert.
    jwt_secret: str = ""
    jwt_secrets: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_lifetime_minutes: int = 30
    jwt_refresh_lifetime_hours: int = 8

    # Cookie fuer Refresh-Token. SameSite=lax, in Produktion zusaetzlich Secure (HTTPS).
    refresh_cookie_name: str = "bws_refresh"
    refresh_cookie_secure: bool = False  # produktiv: True (nur ueber HTTPS)


# Platzhalter aus deploy/.env.example. Wer die Beispieldatei kopiert und nur
# einen Teil ersetzt, wuerde sonst mit dem oeffentlich bekannten Signatur-
# schluessel starten — ein vollstaendiger Auth-Bypass (jeder kann Admin-Tokens
# selbst signieren). Analog zur Platzhalter-Erkennung in security/secrets.py.
_PLACEHOLDER_SECRETS = frozenset({
    "replace-with-openssl-rand-hex-32",
    "replace-with-fernet-generate-key-output",
    "replace-me",
    "replace-me-in-production",
    "changeme",
    "secret",
})

# HS256 mit einem Schluessel < 32 Bytes ist gegen Brute-Force schwach.
_MIN_SECRET_LEN = 32


def _validate_secret(value: str) -> None:
    v = value.strip()
    if v in _PLACEHOLDER_SECRETS:
        raise RuntimeError(
            f"JWT_SECRET steht noch auf dem Platzhalter '{v}' aus "
            "deploy/.env.example. Erzeuge einen echten Schluessel mit "
            "JWT_SECRET=$(openssl rand -hex 32) und setze ihn in der Umgebung."
        )
    if len(v) < _MIN_SECRET_LEN:
        raise RuntimeError(
            f"JWT_SECRET ist mit {len(v)} Zeichen zu kurz (mind. "
            f"{_MIN_SECRET_LEN}). Erzeuge einen mit: openssl rand -hex 32."
        )


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    s = AuthSettings()
    if not s.jwt_secret and not s.jwt_secrets.strip():
        raise RuntimeError(
            "JWT_SECRET (oder JWT_SECRETS als Liste) ist nicht gesetzt. "
            "Setze die Umgebungsvariable, z. B. mit "
            "JWT_SECRET=$(openssl rand -hex 32) — siehe README."
        )
    # Jeden konfigurierten Schluessel pruefen (Sign-Key + Rotations-Keys).
    for key in jwt_secret_keys(s):
        _validate_secret(key)
    return s


def jwt_secret_keys(s: AuthSettings) -> list[str]:
    """Gibt die akzeptierten Secrets zurueck. Erstes = Sign-Key, der Rest =
    nur fuer Verify (Rotation)."""
    keys: list[str] = []
    if s.jwt_secrets.strip():
        keys.extend([k.strip() for k in s.jwt_secrets.split(",") if k.strip()])
    if s.jwt_secret and s.jwt_secret not in keys:
        keys.append(s.jwt_secret)
    return keys


def reset_settings_cache() -> None:
    """Fuer Tests, die die Settings neu laden wollen."""
    get_settings.cache_clear()
