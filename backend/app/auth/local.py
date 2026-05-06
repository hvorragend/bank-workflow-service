"""Lokale Authentifizierung gegen die DB-User-Tabelle.

Reihenfolge:
1. DB-Lookup ueber `users` (auth_source='local', is_active=True).
2. Wenn die DB komplett wegbricht (OperationalError) ODER der User dort nicht
   existiert: Notfall-Lookup gegen die in `bootstrap.get_emergency_users()`
   geladenen Eintraege.

Erfolgreiche Notfall-Logins werden vom Aufrufer (router.py) als
'auth.login.emergency' auditiert.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from .. import models
from ..bootstrap import get_emergency_users
from .schemas import AuthenticatedUser

log = logging.getLogger(__name__)
_hasher = PasswordHasher()
# Konstanter Aufwand: dummy-Verify, damit ein angreifender Beobachter nicht
# durch Antwortzeit ableiten kann, ob ein Username existiert.
_TIMING_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-mitigation")


class LocalAuthError(Exception):
    """Lokale Authentifizierung fehlgeschlagen (User unbekannt oder Passwort falsch)."""


def authenticate_local(db: Session, username: str, password: str) -> AuthenticatedUser:
    """Verifiziert ein User-Passwort gegen den argon2-Hash aus der DB.

    Liefert AuthenticatedUser mit auth_source='local' (regulaer) oder
    'emergency' (Notfall-Datei).
    Raises LocalAuthError bei unbekanntem User oder falschem Passwort.
    """
    # 1. DB-Pfad
    user_row: models.User | None = None
    try:
        user_row = db.scalar(
            select(models.User).where(
                models.User.username == username,
                models.User.auth_source == "local",
                models.User.is_active.is_(True),
            )
        )
    except OperationalError as e:
        log.warning("DB unerreichbar fuer Local-Login (%s) — Notfall-Pfad pruefen.", e)
        return _try_emergency_or_fail(username, password)
    except SQLAlchemyError as e:
        log.warning("DB-Fehler im Local-Login (%s) — Notfall-Pfad pruefen.", e)
        return _try_emergency_or_fail(username, password)

    if user_row is None:
        # User existiert nicht in der DB — vielleicht im Notfall-File.
        emergency = get_emergency_users().get(username)
        if emergency:
            return _verify_emergency(emergency, password)
        # Sonst Konstantzeit-Dummy-Verify und konsistenter Fehler.
        try:
            _hasher.verify(_TIMING_DUMMY_HASH, password)
        except VerificationError:
            pass
        raise LocalAuthError("User nicht gefunden.")

    if not user_row.password_argon2:
        # LDAP-User landen mit auth_source='ldap'; ein Local-User ohne Passwort
        # ist eine inkonsistente Datenlage — wir behandeln ihn als unbekannt.
        raise LocalAuthError("User hat kein lokales Passwort.")

    try:
        _hasher.verify(user_row.password_argon2, password)
    except VerifyMismatchError:
        raise LocalAuthError("Passwort falsch.") from None
    except (InvalidHashError, VerificationError, UnicodeEncodeError, ValueError, TypeError) as e:
        # Ein im users.json hinterlegter Platzhalter wie
        # 'ERSETZEN — Hash aus python -m app.auth.hash_password' enthaelt
        # ein Em-Dash und scheitert bereits an _ensure_bytes (UnicodeEncodeError);
        # ein nur-ASCII-Platzhalter scheitert an InvalidHashError. Beides
        # wuerde sonst als ungefangene Exception zu 500/502 hinter dem
        # Reverse-Proxy fuehren. Wir behandeln das wie einen unbekannten
        # User und geben dem Operator einen klaren Hinweis ins Log.
        log.error(
            "User '%s' hat einen ungueltigen argon2-Hash in der DB (%s: %s). "
            "Wahrscheinlich wurde der Platzhalter aus users.example.json "
            "uebernommen, ohne mit 'python -m app.auth.hash_password' einen "
            "echten Hash zu erzeugen. Login wird als 401 abgewiesen.",
            username,
            type(e).__name__,
            e,
        )
        raise LocalAuthError("User hat keinen gueltigen Passwort-Hash.") from None

    user_row.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return _to_authenticated_user_db(db, user_row)


def is_local_user(db: Session, username: str) -> bool:
    """True, wenn der User in der users-Tabelle als auth_source='local' existiert.
    Faellt bei DB-Fehlern auf das Notfall-File zurueck.
    """
    try:
        return db.scalar(
            select(models.User.id).where(
                models.User.username == username,
                models.User.auth_source == "local",
                models.User.is_active.is_(True),
            )
        ) is not None
    except SQLAlchemyError:
        return username in get_emergency_users()


def resolve_user_permissions(db: Session, user_row: models.User) -> tuple[list[str], list[str]]:
    """Liefert (role_names, permission_codes) fuer den Login-Zeitpunkt."""
    role_names: list[str] = []
    perm_codes: set[str] = set()
    for role in user_row.roles:
        role_names.append(role.name)
        for perm in role.permissions:
            perm_codes.add(perm.code)
    return sorted(set(role_names)), sorted(perm_codes)


# ----------------------------------------------------------------- internals


def _to_authenticated_user_db(db: Session, u: models.User) -> AuthenticatedUser:
    roles, perms = resolve_user_permissions(db, u)
    return AuthenticatedUser(
        username=u.username,
        name=u.display_name,
        email=u.email or "",
        roles=roles,
        permissions=perms,
        auth_source="local",
    )


def _try_emergency_or_fail(username: str, password: str) -> AuthenticatedUser:
    emergency = get_emergency_users().get(username)
    if not emergency:
        try:
            _hasher.verify(_TIMING_DUMMY_HASH, password)
        except VerificationError:
            pass
        raise LocalAuthError("User nicht gefunden (DB unerreichbar, Notfall-User unbekannt).")
    return _verify_emergency(emergency, password)


def _verify_emergency(eu, password: str) -> AuthenticatedUser:
    try:
        _hasher.verify(eu.password_argon2, password)
    except VerifyMismatchError:
        raise LocalAuthError("Passwort falsch.") from None
    except (InvalidHashError, VerificationError, UnicodeEncodeError, ValueError, TypeError) as e:
        log.error(
            "Notfall-User '%s' hat einen ungueltigen argon2-Hash in "
            "emergency_users.json (%s: %s). Hash bitte mit "
            "'python -m app.auth.hash_password' neu erzeugen.",
            eu.username,
            type(e).__name__,
            e,
        )
        raise LocalAuthError("Notfall-User hat keinen gueltigen Passwort-Hash.") from None
    return AuthenticatedUser(
        username=eu.username,
        name=eu.display_name,
        email=eu.email,
        roles=list(eu.roles),
        permissions=list(eu.permissions),
        auth_source="emergency",
    )
