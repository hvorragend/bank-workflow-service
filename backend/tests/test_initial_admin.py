"""Tests fuer den Greenfield-Initial-Admin (bootstrap.ensure_initial_admin).

Die Tests arbeiten bewusst auf einer eigenen, frischen SQLite-DB (nicht auf der
conftest-Session-DB), weil es genau um den Zustand "leere DB, keine Notfall-
Datei" geht — den die conftest-Umgebung per Design nie hat.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def fresh_db(tmp_path: Path):
    """Frische SQLite-DB mit Permission-Katalog + Admin-Rolle (wie im Lifespan
    VOR ensure_initial_admin), aber ohne User."""
    from app import bootstrap
    from app.models import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'initial_admin.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SL() as db:
        bootstrap.seed_permission_catalog(db)
        bootstrap.ensure_admin_role(db)
        yield db
    engine.dispose()


@pytest.fixture()
def greenfield_env(monkeypatch, tmp_path: Path) -> Path:
    """Env wie bei einer Erstinbetriebnahme: keine Notfall-Datei, Passwort-Datei
    in ein tmp-Verzeichnis. Gibt den Pfad der Passwort-Datei zurueck."""
    pw_file = tmp_path / "initial-admin-password.txt"
    monkeypatch.setenv("EMERGENCY_USERS_PATH", str(tmp_path / "missing-emergency.json"))
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD_FILE", str(pw_file))
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
    return pw_file


def _parse_password_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            out[key] = value
    return out


@pytest.mark.notfall(szenario="Erstinbetriebnahme: leere DB startet ohne manuelle Schritte")
def test_initial_admin_created_on_greenfield(fresh_db, greenfield_env):
    from app import bootstrap
    from app.models import User

    bootstrap.ensure_initial_admin(fresh_db)

    user = fresh_db.scalar(select(User).where(User.username == "admin"))
    assert user is not None, "Initial-Admin muss angelegt werden."
    assert user.is_active
    assert user.auth_source == "local"
    assert {r.name for r in user.roles} == {"Admin"}

    # Generiertes Passwort steht in der Datei und passt zum argon2-Hash.
    creds = _parse_password_file(greenfield_env)
    assert creds["username"] == "admin"
    assert PasswordHasher().verify(user.password_argon2, creds["password"])
    assert (greenfield_env.stat().st_mode & 0o777) == 0o600

    # Danach ist der Admin-Check zufrieden — die App wuerde starten.
    bootstrap.ensure_emergency_admin_or_die(fresh_db)


def test_initial_admin_uses_env_password_without_file(fresh_db, greenfield_env, monkeypatch):
    from app import bootstrap
    from app.models import User

    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "erstadmin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "vorgabe-passwort-123!")
    bootstrap.ensure_initial_admin(fresh_db)

    user = fresh_db.scalar(select(User).where(User.username == "erstadmin"))
    assert user is not None
    assert PasswordHasher().verify(user.password_argon2, "vorgabe-passwort-123!")
    # Explizit gesetztes Passwort landet NICHT auf der Platte.
    assert not greenfield_env.exists()


def test_initial_admin_skipped_when_admin_exists(fresh_db, greenfield_env):
    from app import bootstrap
    from app.models import Role, User, UserRole

    admin_role = fresh_db.scalar(select(Role).where(Role.name == "Admin"))
    existing = User(
        username="bestand", display_name="Bestand", auth_source="local",
        password_argon2=PasswordHasher().hash("x"), is_active=True,
    )
    fresh_db.add(existing)
    fresh_db.flush()
    fresh_db.add(UserRole(user_id=existing.id, role_id=admin_role.id))
    fresh_db.commit()

    bootstrap.ensure_initial_admin(fresh_db)

    assert fresh_db.scalar(select(User).where(User.username == "admin")) is None
    assert not greenfield_env.exists()


def test_initial_admin_skipped_when_emergency_file_exists(fresh_db, greenfield_env, monkeypatch, tmp_path):
    from app import bootstrap
    from app.models import User

    emergency = tmp_path / "emergency_users.json"
    emergency.write_text('{"users": []}', encoding="utf-8")
    monkeypatch.setenv("EMERGENCY_USERS_PATH", str(emergency))

    bootstrap.ensure_initial_admin(fresh_db)

    assert fresh_db.scalar(select(User).where(User.username == "admin")) is None
    assert not greenfield_env.exists()


def test_initial_admin_never_overwrites_existing_username(fresh_db, greenfield_env):
    """Ein User 'admin' ohne Admin-Rolle existiert bereits: Passwort darf NICHT
    ueberschrieben werden, und der harte Startabbruch bleibt bestehen."""
    from app import bootstrap
    from app.models import User

    original_hash = PasswordHasher().hash("altes-passwort")
    fresh_db.add(User(
        username="admin", display_name="Alt", auth_source="local",
        password_argon2=original_hash, is_active=True,
    ))
    fresh_db.commit()

    bootstrap.ensure_initial_admin(fresh_db)

    user = fresh_db.scalar(select(User).where(User.username == "admin"))
    assert user.password_argon2 == original_hash
    assert not greenfield_env.exists()
    with pytest.raises(RuntimeError):
        bootstrap.ensure_emergency_admin_or_die(fresh_db)


def test_initial_admin_writes_audit_event(fresh_db, greenfield_env):
    from app import bootstrap
    from app.models import AuditEvent

    bootstrap.ensure_initial_admin(fresh_db)

    events = list(fresh_db.scalars(select(AuditEvent).where(AuditEvent.action == "user.bootstrap")))
    assert len(events) == 1
    assert events[0].payload["username"] == "admin"
    assert events[0].payload["password_generated"] is True
