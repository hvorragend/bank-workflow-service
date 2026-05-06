"""Lifespan-Helfer fuer den App-Start.

Ablauf in main.lifespan() (Reihenfolge wichtig):

    1. assert_encryption_available()    # frueh scheitern, wenn Key fehlt
    2. seed_permission_catalog(db)      # Permissions aus dem Code-Katalog
    3. ensure_admin_role(db)            # Admin-Rolle haelt automatisch alle Permissions
    4. ensure_singleton_configs(db)     # ldap_config/smtp_config/escalation_config rows id=1
    5. ensure_default_templates(db)     # Notification-Templates, falls leer
    6. import_legacy_files_if_present(db)
    7. ensure_emergency_admin_or_die(db)

Brownfield-Sicher: alle Schritte sind idempotent. Mehrfacher Aufruf macht nichts kaputt.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .auth import permission_catalog
from .security import secrets

log = logging.getLogger("bootstrap")

EMERGENCY_USERS_PATH_DEFAULT = "config/emergency_users.json"


# In-Memory-Registry fuer Notfall-User. Wird von local.py konsultiert,
# wenn die DB unerreichbar ist oder kein Admin existiert.
class EmergencyUser:
    __slots__ = ("username", "display_name", "email", "password_argon2", "roles", "permissions")

    def __init__(self, *, username: str, display_name: str, email: str,
                 password_argon2: str, roles: list[str], permissions: list[str]) -> None:
        self.username = username
        self.display_name = display_name
        self.email = email
        self.password_argon2 = password_argon2
        self.roles = roles
        self.permissions = permissions


_EMERGENCY_USERS: dict[str, EmergencyUser] = {}


def get_emergency_users() -> dict[str, EmergencyUser]:
    """Liefert die geladenen Notfall-User. Leer, solange ensure_emergency_admin_or_die
    noch nicht gelaufen ist (oder die Datei fehlt)."""
    return _EMERGENCY_USERS


def reset_emergency_users() -> None:
    """Fuer Tests."""
    _EMERGENCY_USERS.clear()


def assert_encryption_available() -> None:
    secrets.assert_encryption_available()
    log.info("Verschluesselungs-Schluessel ok (Fingerprint %s).", secrets.key_fingerprint())


def seed_permission_catalog(db: Session) -> dict[str, str]:
    """Stellt sicher, dass jede Permission aus dem Code-Katalog in der DB liegt.
    Gibt {code: id} zurueck."""
    existing: dict[str, models.Permission] = {
        p.code: p for p in db.scalars(select(models.Permission)).all()
    }
    out: dict[str, str] = {}
    added = 0
    for p in permission_catalog.PERMISSIONS:
        if p.code in existing:
            row = existing[p.code]
            # Beschreibung/Area aktualisieren, falls geaendert
            if row.area != p.area or row.description != p.description:
                row.area = p.area
                row.description = p.description
            out[p.code] = row.id
        else:
            row = models.Permission(code=p.code, area=p.area, description=p.description)
            db.add(row)
            db.flush()
            out[p.code] = row.id
            added += 1
    if added:
        log.info("Permission-Katalog: %d neue Permissions ergaenzt.", added)
    db.commit()
    return out


def ensure_default_roles(db: Session) -> None:
    """Stellt sicher, dass die fachlichen Default-Rollen (Vorstand, Compliance, ...)
    existieren — wichtig fuer Tests/Quickstart, wo nur create_all laeuft (ohne Migration)."""
    role_by_name = {r.name: r for r in db.scalars(select(models.Role)).all()}
    perm_by_code = {p.code: p for p in db.scalars(select(models.Permission)).all()}
    for role_name, perm_codes in permission_catalog.DEFAULT_ROLE_PERMISSIONS.items():
        role = role_by_name.get(role_name)
        if role is None:
            role = models.Role(
                name=role_name,
                description=f"Default-Rolle {role_name}",
                is_system=False,
            )
            db.add(role)
            db.flush()
            role_by_name[role_name] = role
        # Permissions auffuellen (nur fehlende ergaenzen, nicht ueberschreiben).
        have = {p.code for p in role.permissions}
        for code in perm_codes:
            perm = perm_by_code.get(code)
            if perm and code not in have:
                db.add(models.RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()


def ensure_admin_role(db: Session) -> models.Role:
    """Garantiert die Existenz der Admin-Rolle und stellt sicher, dass sie alle
    aktuellen Permissions haelt."""
    role = db.scalar(select(models.Role).where(models.Role.name == "Admin"))
    if not role:
        role = models.Role(
            name="Admin",
            description="System-Rolle. Alle Permissions. Nicht loeschbar.",
            is_system=True,
        )
        db.add(role)
        db.flush()
        log.info("Admin-Rolle angelegt.")
    elif not role.is_system:
        # Fix: Admin muss is_system sein.
        role.is_system = True

    all_perms = list(db.scalars(select(models.Permission)).all())
    have_ids = {p.id for p in role.permissions}
    added = 0
    for p in all_perms:
        if p.id not in have_ids:
            db.add(models.RolePermission(role_id=role.id, permission_id=p.id))
            added += 1
    if added:
        log.info("Admin-Rolle: %d Permissions ergaenzt.", added)
    db.commit()
    db.refresh(role)
    return role


def ensure_singleton_configs(db: Session) -> None:
    """Stellt sicher, dass ldap_config/smtp_config/escalation_config je eine
    Row mit id=1 haben."""
    if not db.get(models.LdapConfig, 1):
        db.add(models.LdapConfig(id=1))
    if not db.get(models.SmtpConfig, 1):
        db.add(models.SmtpConfig(id=1))
    if not db.get(models.EscalationConfig, 1):
        bereich = db.scalar(select(models.Role).where(models.Role.name == "Bereichsleiter"))
        db.add(models.EscalationConfig(id=1, bereichsleiter_role_id=bereich.id if bereich else None))
    # Default app_settings
    for key, value in [("auth.mode", "local"), ("auth.login_rate_limit", "5/minute")]:
        if not db.get(models.AppSetting, key):
            db.add(models.AppSetting(key=key, value=value))
    db.commit()


def ensure_default_templates(db: Session) -> None:
    """Wenn die Templates-Tabelle leer ist (frische Installation ohne Migration-Seed),
    fuelle sie aus dem im Code mitgelieferten Default-Set."""
    existing = {t.key for t in db.scalars(select(models.NotificationTemplate)).all()}
    from .notifications.default_templates import DEFAULT_TEMPLATES
    added = 0
    for key, (subject, body) in DEFAULT_TEMPLATES.items():
        if key not in existing:
            db.add(models.NotificationTemplate(key=key, subject=subject, body=body))
            added += 1
    if added:
        log.info("Notification-Templates: %d Defaults ergaenzt.", added)
    db.commit()


def import_legacy_files_if_present(db: Session) -> None:
    """Brownfield: bestehende config/users.json + role_emails.toml in die DB heben.
    Macht nichts, wenn die DB bereits regulaere User enthaelt — dann ist die
    Migration schon einmal durchgelaufen.
    """
    has_regular_users = db.scalar(
        select(models.User.id).where(models.User.is_emergency.is_(False))
    )
    if has_regular_users:
        return

    users_path = Path(_env("USERS_CONFIG_PATH", "config/users.json"))
    if users_path.exists():
        _import_users_json(db, users_path)

    role_emails_path = Path(_env("ROLE_EMAILS_PATH", "config/role_emails.toml"))
    if role_emails_path.exists():
        _import_role_emails_toml(db, role_emails_path)


def ensure_emergency_admin_or_die(db: Session) -> None:
    """Garantiert, dass es einen aktiven Weg ins Admin-Panel gibt:
       1. Es existiert ein aktiver User mit der Permission 'admin.users.write', ODER
       2. config/emergency_users.json ist vorhanden und valide.

    Falls beides fehlt, refused der App-Start mit einer klaren Anleitung.
    """
    if _has_active_admin(db):
        log.info("Admin-User in DB vorhanden — Notfall-Datei nicht noetig.")
        return

    path = Path(_env("EMERGENCY_USERS_PATH", EMERGENCY_USERS_PATH_DEFAULT))
    if not path.exists():
        raise RuntimeError(
            "Kein aktiver Admin-User in der DB und keine Notfall-Datei "
            f"({path}). Bitte legen Sie eine Notfall-Datei nach dem Muster aus "
            "config/emergency_users.example.json an oder seeden Sie einen Admin "
            "in die users-Tabelle."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = _load_emergency_users(raw)
    if not loaded:
        raise RuntimeError(
            "Kein aktiver Admin-User in der DB und Notfall-Datei enthielt "
            "keine validen Eintraege."
        )
    _EMERGENCY_USERS.clear()
    _EMERGENCY_USERS.update(loaded)
    log.warning(
        "Kein DB-Admin gefunden — Notfall-Login aktiv mit Usern: %s.",
        ", ".join(loaded.keys()),
    )


# ------------------------------------------------------------------ helpers


def _env(name: str, default: str) -> str:
    import os
    return os.getenv(name, default)


def _has_active_admin(db: Session) -> bool:
    """True, wenn ein aktiver User existiert, der admin.users.write besitzt."""
    perm = db.scalar(
        select(models.Permission).where(models.Permission.code == "admin.users.write")
    )
    if not perm:
        return False
    rows = db.execute(
        select(models.User.id)
        .join(models.UserRole, models.UserRole.user_id == models.User.id)
        .join(models.RolePermission, models.RolePermission.role_id == models.UserRole.role_id)
        .where(
            models.RolePermission.permission_id == perm.id,
            models.User.is_active.is_(True),
        )
        .limit(1)
    ).first()
    return rows is not None


def _import_users_json(db: Session, path: Path) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Konnte %s nicht lesen: %s", path, e)
        return
    role_by_name: dict[str, models.Role] = {
        r.name: r for r in db.scalars(select(models.Role)).all()
    }
    added = 0
    for entry in raw.get("users", []):
        username = entry.get("username")
        if not username or entry.get("is_emergency"):
            continue
        if db.scalar(select(models.User).where(models.User.username == username)):
            continue
        u = models.User(
            username=username,
            display_name=entry.get("name") or username,
            email=entry.get("email") or None,
            auth_source="local",
            password_argon2=entry.get("password_argon2"),
            is_active=True,
        )
        db.add(u)
        db.flush()
        for role_name in entry.get("roles", []):
            role = role_by_name.get(role_name)
            if role:
                db.add(models.UserRole(user_id=u.id, role_id=role.id))
        added += 1
    if added:
        log.info("Brownfield-Import: %d User aus %s uebernommen.", added, path)
        db.commit()


def _import_role_emails_toml(db: Session, path: Path) -> None:
    try:
        import tomllib
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        log.warning("Konnte %s nicht lesen: %s", path, e)
        return
    role_by_name: dict[str, models.Role] = {
        r.name: r for r in db.scalars(select(models.Role)).all()
    }
    added = 0
    for role_name, addrs in raw.get("role_emails", {}).items():
        role = role_by_name.get(role_name)
        if not role or not isinstance(addrs, list):
            continue
        for addr in addrs:
            if not isinstance(addr, str) or not addr.strip():
                continue
            exists = db.scalar(
                select(models.RoleEmail.id).where(
                    models.RoleEmail.role_id == role.id,
                    models.RoleEmail.email == addr.strip(),
                )
            )
            if exists:
                continue
            db.add(models.RoleEmail(role_id=role.id, email=addr.strip()))
            added += 1
    if added:
        log.info("Brownfield-Import: %d Rollen-E-Mails aus %s uebernommen.", added, path)
        db.commit()


def _load_emergency_users(raw: dict) -> dict[str, EmergencyUser]:
    """Akzeptiert dasselbe Format wie config/users.json. Notfall-User bekommen
    automatisch die Permissions, die fuer einen Admin-Login noetig sind —
    egal welche 'roles' im File stehen, damit ein Tippfehler nicht aussperrt.
    """
    out: dict[str, EmergencyUser] = {}
    full_perms = permission_catalog.all_codes()  # alles erlauben
    for entry in raw.get("users", []):
        username = entry.get("username")
        pw_hash = entry.get("password_argon2")
        if not username or not pw_hash:
            continue
        out[username] = EmergencyUser(
            username=username,
            display_name=entry.get("name") or username,
            email=entry.get("email") or "",
            password_argon2=pw_hash,
            roles=list(entry.get("roles") or ["Admin"]),
            permissions=full_perms,
        )
    return out


# Optional: CLI-Helfer, um aus User-Eingabe einen Argon2-Hash zu erzeugen.
# Ruft bestehende app/auth/hash_password.py nicht direkt — die ist als __main__ gedacht.
def hash_password(password: str) -> str:
    return PasswordHasher().hash(password)


# Re-export, damit andere Module nicht mehrere Imports brauchen.
__all__ = [
    "assert_encryption_available",
    "seed_permission_catalog",
    "ensure_default_roles",
    "ensure_admin_role",
    "ensure_singleton_configs",
    "ensure_default_templates",
    "import_legacy_files_if_present",
    "ensure_emergency_admin_or_die",
    "get_emergency_users",
    "reset_emergency_users",
    "EmergencyUser",
]
