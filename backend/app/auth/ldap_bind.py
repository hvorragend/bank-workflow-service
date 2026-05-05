"""LDAP-Authentifizierung via ldap3.

Drei Fehlerklassen, damit der Login-Flow den Fall „LDAP nicht erreichbar"
sauber von „User unbekannt" und „Passwort falsch" trennen kann — wichtig
fuer den AUTH_MODE='both'-Fallback.
"""
from __future__ import annotations

import logging
import ssl

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import (
    LDAPBindError,
    LDAPException,
    LDAPInvalidCredentialsResult,
    LDAPSocketOpenError,
)

from .config import LdapConfig, load_ldap_config
from .schemas import AuthenticatedUser

log = logging.getLogger(__name__)


class LdapServerUnreachable(Exception):
    """LDAP-Server nicht erreichbar (Timeout, Netzwerk, TLS-Fehler)."""


class LdapUserUnknown(Exception):
    """LDAP-Server hat geantwortet, kennt den User aber nicht."""


class LdapBadCredentials(Exception):
    """LDAP-Server hat geantwortet: User existiert, Passwort falsch."""


def authenticate_ldap(username: str, password: str) -> AuthenticatedUser:
    """Bindet gegen LDAPS, sucht Gruppen, mappt auf Rollen.

    Raises:
        LdapServerUnreachable: Server-Probleme — Aufrufer kann auf Local fallen.
        LdapUserUnknown: User-DN nicht auffindbar — Aufrufer kann auf Local fallen.
        LdapBadCredentials: Bind hat „invalid credentials" geliefert — KEIN Fallback.
    """
    cfg = load_ldap_config()
    if not cfg.server:
        raise LdapServerUnreachable("LDAP nicht konfiguriert.")
    if not cfg.server.startswith("ldaps://") and cfg.tls_required:
        raise LdapServerUnreachable("LDAP erfordert ldaps:// (Klartext-Bind nicht erlaubt).")

    tls = _build_tls(cfg)
    try:
        server = Server(cfg.server, get_info=ALL, tls=tls, connect_timeout=cfg.timeout_seconds)
    except LDAPException as e:
        raise LdapServerUnreachable(f"Server-Initialisierung fehlgeschlagen: {e}") from e

    user_dn = cfg.bind_user_template.format(username=username)
    try:
        with Connection(server, user=user_dn, password=password, auto_bind=True) as conn:
            roles = _lookup_roles(conn, cfg, user_dn)
            display_name, email = _lookup_attributes(conn, cfg, user_dn)
    except LDAPInvalidCredentialsResult:
        # User existiert (oder DN-Pattern war richtig), Passwort war falsch.
        raise LdapBadCredentials("LDAP: Passwort falsch.") from None
    except LDAPBindError as e:
        # Differenzierung schwer; behandeln wir konservativ als „User unbekannt"
        # (kein Fallback-Risiko, weil keine LDAP-Credentials akzeptiert wurden).
        raise LdapUserUnknown(f"LDAP-Bind fehlgeschlagen: {e}") from e
    except LDAPSocketOpenError as e:
        raise LdapServerUnreachable(f"LDAP-Verbindung fehlgeschlagen: {e}") from e
    except LDAPException as e:
        raise LdapServerUnreachable(f"LDAP-Fehler: {e}") from e

    return AuthenticatedUser(
        username=username,
        name=display_name or username,
        email=email,
        roles=roles,
        auth_source="ldap",
    )


def _build_tls(cfg: LdapConfig) -> Tls | None:
    if not cfg.server.startswith("ldaps://"):
        return None
    if cfg.ca_cert:
        return Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=cfg.ca_cert)
    return Tls(validate=ssl.CERT_REQUIRED)


def _lookup_roles(conn: Connection, cfg: LdapConfig, user_dn: str) -> list[str]:
    if not cfg.group_search_base or not cfg.role_mapping:
        return []
    flt = cfg.group_filter.format(user_dn=user_dn)
    conn.search(cfg.group_search_base, flt, search_scope=SUBTREE, attributes=["dn"])
    roles: set[str] = set()
    for entry in conn.entries:
        dn = str(entry.entry_dn)
        for mapped in cfg.role_mapping.get(dn, []):
            roles.add(mapped)
    return sorted(roles)


def _lookup_attributes(conn: Connection, cfg: LdapConfig, user_dn: str) -> tuple[str, str]:
    if not cfg.search_base:
        return "", ""
    conn.search(user_dn, "(objectClass=*)", attributes=["displayName", "mail", "cn"])
    if not conn.entries:
        return "", ""
    e = conn.entries[0]
    name = ""
    email = ""
    if "displayName" in e:
        name = str(e.displayName)
    elif "cn" in e:
        name = str(e.cn)
    if "mail" in e:
        email = str(e.mail)
    return name, email
