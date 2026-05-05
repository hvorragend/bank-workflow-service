"""Lokales User-Verzeichnis aus config/users.json — Fallback fuer LDAP."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import LocalUser, load_local_users
from .schemas import AuthenticatedUser

_hasher = PasswordHasher()
# Einmal-Hash fuer Timing-Attack-Mitigation: aehnlicher Aufwand wie ein echter Verify,
# wenn der Username nicht existiert.
_TIMING_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-mitigation")


class LocalAuthError(Exception):
    """Lokale Authentifizierung fehlgeschlagen (User unbekannt oder Passwort falsch)."""


def authenticate_local(username: str, password: str) -> AuthenticatedUser:
    """Verifiziert ein User-Passwort gegen den argon2-Hash aus users.json.

    Raises LocalAuthError bei unbekanntem User oder falschem Passwort. Gibt eine
    AuthenticatedUser mit auth_source='local' zurueck.
    """
    users = load_local_users()
    user = users.get(username)
    if user is None:
        # Konstanter Aufwand: dummy-Verify, damit ein angreifender Beobachter nicht
        # durch Antwortzeit ableiten kann, ob ein Username existiert.
        try:
            _hasher.verify(_TIMING_DUMMY_HASH, password)
        except VerifyMismatchError:
            pass
        raise LocalAuthError("User nicht gefunden.")

    try:
        _hasher.verify(user.password_argon2, password)
    except VerifyMismatchError:
        raise LocalAuthError("Passwort falsch.") from None

    return _to_authenticated_user(user)


def is_local_user(username: str) -> bool:
    """True, wenn der User in users.json gelistet ist."""
    return username in load_local_users()


def _to_authenticated_user(u: LocalUser) -> AuthenticatedUser:
    return AuthenticatedUser(
        username=u.username,
        name=u.name,
        email=u.email,
        roles=list(u.roles),
        auth_source="local",
    )
