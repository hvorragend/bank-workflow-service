"""LDAP-Authentifizierung via ldap3.

Konfiguration kommt aus der DB (ldap_config-Tabelle, geladen ueber
config_service.ldap_settings). Drei Fehlerklassen, damit der Login-Flow den
Fall „LDAP nicht erreichbar" sauber von „User unbekannt" und „Passwort falsch"
trennen kann — wichtig fuer den AUTH_MODE='both'-Fallback.
"""
from __future__ import annotations

import logging
import ssl
import tempfile
from pathlib import Path

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import (
    LDAPBindError,
    LDAPException,
    LDAPInvalidCredentialsResult,
    LDAPSocketOpenError,
)
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import escape_rdn

from ..config_service.ldap_settings import LdapSettings
from .schemas import AuthenticatedUser

log = logging.getLogger(__name__)


class LdapServerUnreachable(Exception):
    """LDAP-Server nicht erreichbar (Timeout, Netzwerk, TLS-Fehler)."""


class LdapUserUnknown(Exception):
    """LDAP-Server hat geantwortet, kennt den User aber nicht."""


class LdapBadCredentials(Exception):
    """LDAP-Server hat geantwortet: User existiert, Passwort falsch."""


def authenticate_ldap(cfg: LdapSettings, username: str, password: str) -> AuthenticatedUser:
    """Bindet gegen LDAPS, sucht Gruppen, mappt auf Rollen.

    Raises:
        LdapServerUnreachable: Server-Probleme — Aufrufer kann auf Local fallen.
        LdapUserUnknown: User-DN nicht auffindbar — Aufrufer kann auf Local fallen.
        LdapBadCredentials: Bind hat „invalid credentials" geliefert — KEIN Fallback.
    """
    if not cfg.enabled or not cfg.server:
        raise LdapServerUnreachable("LDAP nicht konfiguriert oder deaktiviert.")
    if not cfg.server.startswith("ldaps://") and cfg.tls_required:
        raise LdapServerUnreachable("LDAP erfordert ldaps:// (Klartext-Bind nicht erlaubt).")

    tls, ca_path = _build_tls(cfg)
    try:
        try:
            server = Server(cfg.server, get_info=ALL, tls=tls, connect_timeout=cfg.timeout_seconds)
        except LDAPException as e:
            raise LdapServerUnreachable(f"Server-Initialisierung fehlgeschlagen: {e}") from e

        # F-021: den vom Client gelieferten Username DN-escapen, bevor er in das
        # Bind-DN-Template eingesetzt wird (LDAP-Injection ueber z.B. Kommas).
        user_dn = cfg.bind_user_template.format(username=escape_rdn(username))
        try:
            with Connection(server, user=user_dn, password=password, auto_bind=True) as conn:
                roles = _lookup_roles(conn, cfg, user_dn)
                display_name, email = _lookup_attributes(conn, cfg, user_dn)
        except LDAPInvalidCredentialsResult:
            raise LdapBadCredentials("LDAP: Passwort falsch.") from None
        except LDAPBindError as e:
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
            permissions=[],  # werden vom Login-Handler aus DB-Rollen aufgeloest
            auth_source="ldap",
        )
    finally:
        # F-043: die CA-PEM-Tempdatei nach dem Bind wieder entfernen, damit sie
        # nicht bei jedem Login auf der Platte liegen bleibt.
        if ca_path:
            Path(ca_path).unlink(missing_ok=True)


def _build_tls(cfg: LdapSettings) -> tuple[Tls | None, str | None]:
    """Baut das Tls-Objekt und gibt zusaetzlich den Pfad einer ggf. erzeugten
    CA-PEM-Tempdatei zurueck, damit der Aufrufer sie nach Gebrauch loeschen kann
    (F-043). Zweites Tupel-Element ist None, wenn keine Datei erzeugt wurde."""
    if not cfg.server.startswith("ldaps://"):
        return None, None
    if cfg.ca_cert_pem:
        # ldap3 will einen Pfad — wir schreiben das PEM in eine Tempdatei. ldap3
        # liest den Pfad erst beim Verbindungsaufbau, daher darf die Datei erst
        # NACH dem Bind geloescht werden (siehe finally im Aufrufer).
        f = tempfile.NamedTemporaryFile(prefix="bws-ldap-ca-", suffix=".pem", delete=False)
        try:
            f.write(cfg.ca_cert_pem.encode("utf-8"))
            f.flush()
            ca_path = f.name
        finally:
            f.close()
        return Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=ca_path), ca_path
    return Tls(validate=ssl.CERT_REQUIRED), None


def _lookup_roles(conn: Connection, cfg: LdapSettings, user_dn: str) -> list[str]:
    if not cfg.group_search_base or not cfg.role_mapping:
        return []
    # F-021: user_dn kann aus dem (bereits escapten) Bind-Template stammen,
    # wird hier aber in einen Suchfilter eingesetzt — dort gelten andere
    # Sonderzeichen, daher zusaetzlich escape_filter_chars.
    flt = cfg.group_filter.format(user_dn=escape_filter_chars(user_dn))
    conn.search(cfg.group_search_base, flt, search_scope=SUBTREE, attributes=["dn"])
    roles: set[str] = set()
    for entry in conn.entries:
        dn = str(entry.entry_dn)
        for mapped in cfg.role_mapping.get(dn, []):
            roles.add(mapped)
    return sorted(roles)


def _lookup_attributes(conn: Connection, cfg: LdapSettings, user_dn: str) -> tuple[str, str]:
    if not cfg.search_base:
        return "", ""
    conn.search(user_dn, "(objectClass=*)",
                attributes=[cfg.attr_display_name, cfg.attr_email, "cn"])
    if not conn.entries:
        return "", ""
    e = conn.entries[0]
    name = ""
    email = ""
    if cfg.attr_display_name in e:
        name = str(e[cfg.attr_display_name])
    elif "cn" in e:
        name = str(e.cn)
    if cfg.attr_email in e:
        email = str(e[cfg.attr_email])
    return name, email
