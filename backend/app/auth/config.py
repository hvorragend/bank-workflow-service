"""Auth-Konfiguration aus Env-Vars und (optional) externen Config-Dateien.

Layout:

- AuthSettings  — Laufzeitparameter aus Env-Vars (Modus, JWT, Pfade)
- LocalUser     — ein Eintrag aus config/users.json
- LdapConfig    — Server, Bind-Template, Gruppen-Mapping aus config/ldap.toml

Die Config-Dateien werden bei jedem Aufruf neu gelesen — sie sind klein, und
Caching macht Tests fragil.
"""
from __future__ import annotations

import json
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocalUser(BaseModel):
    """Ein lokaler Fallback-User aus config/users.json."""

    username: str
    password_argon2: str = Field(
        ..., description="argon2id-Hash, erzeugt mit `python -m app.auth.hash_password`"
    )
    name: str
    email: str = ""
    roles: list[str] = Field(default_factory=list)


class LdapConfig(BaseModel):
    """LDAP-Anbindung. Werte aus config/ldap.toml, alle optional bis zum echten Einsatz."""

    server: str = ""
    bind_user_template: str = "cn={username},ou=Users,dc=example,dc=org"
    search_base: str = ""
    group_search_base: str = ""
    group_filter: str = "(member={user_dn})"
    tls_required: bool = True
    ca_cert: str = ""
    timeout_seconds: int = 5
    role_mapping: dict[str, list[str]] = Field(default_factory=dict)


class AuthSettings(BaseSettings):
    """Laufzeit-Konfiguration aus Env-Vars."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # local | ldap | both — siehe README.
    auth_mode: Literal["local", "ldap", "both"] = "local"

    # JWT-Schluessel. Pflicht; im Test wird er ueber conftest gesetzt.
    # Schluesselrotation: JWT_SECRETS kann eine komma-separierte Liste enthalten —
    # das erste Element wird zum Signieren verwendet, alle anderen werden beim
    # Verify ebenfalls akzeptiert. So lassen sich Keys rotieren, ohne aktive
    # Sessions zu invalidieren.
    jwt_secret: str = ""
    jwt_secrets: str = ""  # optional: "neuestes,zweitneuestes,…"
    jwt_algorithm: str = "HS256"
    jwt_access_lifetime_minutes: int = 30
    jwt_refresh_lifetime_hours: int = 8

    # Cookie fuer Refresh-Token. SameSite=lax, in Produktion zusaetzlich Secure (HTTPS).
    refresh_cookie_name: str = "bws_refresh"
    refresh_cookie_secure: bool = False  # produktiv: True (nur ueber HTTPS)

    # Pfade zu Config-Dateien (relativ zum CWD oder absolut).
    users_config_path: str = "config/users.json"
    ldap_config_path: str = "config/ldap.toml"

    # Login-Rate-Limit (slowapi-Format).
    login_rate_limit: str = "5/minute"


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    """Settings als Singleton (eine Instanz pro Prozess)."""
    s = AuthSettings()
    # Mindestens ein Secret muss gesetzt sein — entweder als Singleton (jwt_secret)
    # oder als Liste (jwt_secrets, komma-separiert).
    if not s.jwt_secret and not s.jwt_secrets.strip():
        raise RuntimeError(
            "JWT_SECRET (oder JWT_SECRETS als Liste) ist nicht gesetzt. "
            "Setze die Umgebungsvariable, z. B. mit "
            "JWT_SECRET=$(openssl rand -hex 32) — siehe README."
        )
    return s


def jwt_secret_keys(s: AuthSettings) -> list[str]:
    """Gibt die akzeptierten Secrets zurueck. Erstes = Sign-Key, der Rest =
    nur fuer Verify (Rotation)."""
    keys: list[str] = []
    if s.jwt_secrets.strip():
        keys.extend([k.strip() for k in s.jwt_secrets.split(",") if k.strip()])
    if s.jwt_secret and s.jwt_secret not in keys:
        # Fallback: wenn nur das Singleton gesetzt ist, ist es zugleich der Sign-Key.
        keys.append(s.jwt_secret)
    return keys


def reset_settings_cache() -> None:
    """Fuer Tests, die die Settings neu laden wollen."""
    get_settings.cache_clear()


def load_local_users(path: str | Path | None = None) -> dict[str, LocalUser]:
    """Liest die lokalen User aus config/users.json. Gibt {} zurueck, wenn die Datei fehlt."""
    p = Path(path) if path is not None else Path(get_settings().users_config_path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {entry["username"]: LocalUser(**entry) for entry in raw.get("users", [])}


def load_ldap_config(path: str | Path | None = None) -> LdapConfig:
    """Liest die LDAP-Konfiguration aus TOML. Gibt LdapConfig() zurueck, wenn Datei fehlt."""
    p = Path(path) if path is not None else Path(get_settings().ldap_config_path)
    if not p.exists():
        return LdapConfig()
    with p.open("rb") as f:
        raw = tomllib.load(f)
    body = dict(raw.get("ldap", {}))
    body["role_mapping"] = raw.get("role_mapping", {})
    return LdapConfig(**body)


def list_known_roles() -> list[str]:
    """Vereinigt alle Rollen aus lokalen Usern und LDAP-Mapping zu einer
    sortierten Liste. Wird vom Designer fuer das Rollen-Dropdown genutzt."""
    roles: set[str] = set()
    for user in load_local_users().values():
        roles.update(user.roles)
    ldap = load_ldap_config()
    for mapped in ldap.role_mapping.values():
        if isinstance(mapped, list):
            roles.update(mapped)
    return sorted(r for r in roles if r and isinstance(r, str))
