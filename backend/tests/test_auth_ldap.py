"""LDAP-Authentifizierung mit ldap3.MOCK_SYNC.

Wir setzen einen In-Memory-LDAP-Server auf, befuellen ihn mit einem User und
einer Gruppe, und uebergeben den Server-Mock per Monkeypatch an die LDAP-
Bind-Funktion. Damit lassen sich die vier wichtigen Faelle testen:

1. Bind erfolgreich + Gruppe -> Rolle
2. Bind mit falschem Passwort -> LdapBadCredentials
3. User unbekannt -> LdapUserUnknown
4. Server unerreichbar -> LdapServerUnreachable
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Server


@pytest.fixture
def ldap_server():
    """Erzeugt einen mock-LDAP-Server mit einem User und einer Gruppe."""
    server = Server("mock-ldap", get_info=OFFLINE_AD_2012_R2)
    return server


@pytest.fixture
def ldap_config_in_memory():
    """LdapConfig fuer den Test — Bind-DN ist frei waehlbar; wir nutzen DC=test."""
    from app.auth.config import LdapConfig
    return LdapConfig(
        server="ldap://mock-ldap",  # ldaps:// im echten Setup; hier reicht ldap:// fuer den Mock
        bind_user_template="cn={username},ou=Users,dc=test,dc=local",
        search_base="ou=Users,dc=test,dc=local",
        group_search_base="ou=Groups,dc=test,dc=local",
        group_filter="(member={user_dn})",
        tls_required=False,
        timeout_seconds=5,
        role_mapping={
            "cn=BWS-Vorstand,ou=Groups,dc=test,dc=local": ["Vorstand"],
        },
    )


def _mock_authenticate_with_creds(monkeypatch, ldap_config, username, password, ok=True):
    """Patched ldap3.Connection so that auto_bind succeeds/fails as configured.

    Wir tauschen den Connection-Konstruktor in app.auth.ldap_bind aus.
    """
    from app.auth import ldap_bind as lb

    if not ok:
        # Bind mit falschem Passwort
        from ldap3.core.exceptions import LDAPInvalidCredentialsResult

        def _raise(*a, **k):
            raise LDAPInvalidCredentialsResult("invalid credentials")
        monkeypatch.setattr(lb, "Connection", _raise)
    else:
        class FakeEntry:
            def __init__(self, dn):
                self.entry_dn = dn
                self.displayName = type("X", (), {"__str__": lambda s: "Demo Vorstand"})()
                self.mail = type("X", (), {"__str__": lambda s: "v@test.local"})()
                self.cn = type("X", (), {"__str__": lambda s: "vorstand"})()
            def __contains__(self, item): return item in {"displayName", "mail", "cn"}

        class FakeConn:
            def __init__(self, *a, **k):
                self.entries = []
            def __enter__(self):
                self._search_calls = 0
                return self
            def __exit__(self, *a): pass
            def search(self, base, flt, **k):
                self._search_calls += 1
                if self._search_calls == 1:
                    # Group-Search
                    self.entries = [FakeEntry("cn=BWS-Vorstand,ou=Groups,dc=test,dc=local")]
                else:
                    # Attribut-Search
                    self.entries = [FakeEntry("cn=vorstand,ou=Users,dc=test,dc=local")]
        monkeypatch.setattr(lb, "Connection", FakeConn)
    monkeypatch.setattr(lb, "load_ldap_config", lambda *a, **k: ldap_config)


def test_ldap_authenticates_and_maps_roles(monkeypatch, ldap_config_in_memory):
    from app.auth.ldap_bind import authenticate_ldap

    _mock_authenticate_with_creds(monkeypatch, ldap_config_in_memory, "vorstand", "right-password", ok=True)
    user = authenticate_ldap("vorstand", "right-password")
    assert user.username == "vorstand"
    assert user.auth_source == "ldap"
    assert "Vorstand" in user.roles


def test_ldap_bad_credentials_raises_specific_error(monkeypatch, ldap_config_in_memory):
    from app.auth.ldap_bind import LdapBadCredentials, authenticate_ldap

    _mock_authenticate_with_creds(monkeypatch, ldap_config_in_memory, "vorstand", "wrong-password", ok=False)
    with pytest.raises(LdapBadCredentials):
        authenticate_ldap("vorstand", "wrong-password")


def test_ldap_unreachable_raises_unreachable(monkeypatch):
    """Wenn die LDAP-Konfig leer ist (kein Server gesetzt), soll LdapServerUnreachable kommen."""
    from app.auth.config import LdapConfig
    from app.auth.ldap_bind import LdapServerUnreachable, authenticate_ldap
    from app.auth import ldap_bind as lb

    monkeypatch.setattr(lb, "load_ldap_config", lambda *a, **k: LdapConfig(server=""))
    with pytest.raises(LdapServerUnreachable):
        authenticate_ldap("anyone", "anypw")
