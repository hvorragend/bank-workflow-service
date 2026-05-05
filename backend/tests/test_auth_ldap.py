"""LDAP-Authentifizierung mit ldap3-Mocks.

Wir setzen einen In-Memory-LDAP-Server auf, befuellen ihn mit einem User und
einer Gruppe, und uebergeben den Server-Mock per Monkeypatch an die LDAP-
Bind-Funktion. Damit lassen sich die wichtigsten Faelle testen.

Seit dem Admin-Panel nimmt authenticate_ldap eine LdapSettings-Konfiguration
als Argument entgegen — wir bauen die hier direkt im Test.
"""
from __future__ import annotations

import pytest
from ldap3 import OFFLINE_AD_2012_R2, Server


@pytest.fixture
def ldap_server():
    server = Server("mock-ldap", get_info=OFFLINE_AD_2012_R2)
    return server


@pytest.fixture
def ldap_config_in_memory():
    """LdapSettings fuer den Test."""
    from app.config_service.ldap_settings import LdapSettings
    return LdapSettings(
        enabled=True,
        server="ldap://mock-ldap",
        bind_user_template="cn={username},ou=Users,dc=test,dc=local",
        search_base="ou=Users,dc=test,dc=local",
        group_search_base="ou=Groups,dc=test,dc=local",
        group_filter="(member={user_dn})",
        tls_required=False,
        timeout_seconds=5,
        attr_display_name="displayName",
        attr_email="mail",
        role_mapping={
            "cn=BWS-Vorstand,ou=Groups,dc=test,dc=local": ["Vorstand"],
        },
    )


def _patch_connection(monkeypatch, ok: bool) -> None:
    from app.auth import ldap_bind as lb

    if not ok:
        from ldap3.core.exceptions import LDAPInvalidCredentialsResult

        def _raise(*a, **k):
            raise LDAPInvalidCredentialsResult("invalid credentials")
        monkeypatch.setattr(lb, "Connection", _raise)
        return

    class FakeEntry:
        def __init__(self, dn):
            self.entry_dn = dn
            self.displayName = type("X", (), {"__str__": lambda s: "Demo Vorstand"})()
            self.mail = type("X", (), {"__str__": lambda s: "v@test.local"})()
            self.cn = type("X", (), {"__str__": lambda s: "vorstand"})()

        def __contains__(self, item):
            return item in {"displayName", "mail", "cn"}

        def __getitem__(self, item):
            return getattr(self, item)

    class FakeConn:
        def __init__(self, *a, **k):
            self.entries = []

        def __enter__(self):
            self._search_calls = 0
            return self

        def __exit__(self, *a):
            pass

        def search(self, base, flt, **k):
            self._search_calls += 1
            if self._search_calls == 1:
                self.entries = [FakeEntry("cn=BWS-Vorstand,ou=Groups,dc=test,dc=local")]
            else:
                self.entries = [FakeEntry("cn=vorstand,ou=Users,dc=test,dc=local")]

    monkeypatch.setattr(lb, "Connection", FakeConn)


def test_ldap_authenticates_and_maps_roles(monkeypatch, ldap_config_in_memory):
    from app.auth.ldap_bind import authenticate_ldap

    _patch_connection(monkeypatch, ok=True)
    user = authenticate_ldap(ldap_config_in_memory, "vorstand", "right-password")
    assert user.username == "vorstand"
    assert user.auth_source == "ldap"
    assert "Vorstand" in user.roles


def test_ldap_bad_credentials_raises_specific_error(monkeypatch, ldap_config_in_memory):
    from app.auth.ldap_bind import LdapBadCredentials, authenticate_ldap

    _patch_connection(monkeypatch, ok=False)
    with pytest.raises(LdapBadCredentials):
        authenticate_ldap(ldap_config_in_memory, "vorstand", "wrong-password")


def test_ldap_unreachable_raises_unreachable():
    """Wenn die LDAP-Konfig leer ist (kein Server gesetzt), soll LdapServerUnreachable kommen."""
    from app.auth.ldap_bind import LdapServerUnreachable, authenticate_ldap
    from app.config_service.ldap_settings import LdapSettings

    cfg = LdapSettings(enabled=True, server="")
    with pytest.raises(LdapServerUnreachable):
        authenticate_ldap(cfg, "anyone", "anypw")
