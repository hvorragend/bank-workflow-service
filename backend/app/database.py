"""SQLAlchemy-2.0-Setup.

Datenbankwahl ueber Umgebungsvariable `DATABASE_URL`:

- Standard fuer lokales Loslegen: SQLite-Datei `bank_workflow.db` (kein Setup noetig).
- Empfohlen fuer Entwicklung gegen produktionsnahe Daten:
    docker compose -f deploy/docker-compose.dev.yml up -d   # startet Postgres
    export DATABASE_URL=postgresql+psycopg://bws:bws_local_dev@localhost:5432/bws
- Produktion (Container-Stack): `DATABASE_URL` zeigt auf den Postgres-Service,
  z. B. `postgresql+psycopg://bws:${PG_PASSWORD}@postgres:5432/bws`.

Schema-Migrationen werden ueber Alembic gepflegt (`alembic upgrade head`).
`Base.metadata.create_all(...)` im Lifespan dient nur dem Schnellstart und
ist mit der Initial-Migration deckungsgleich.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bank_workflow.db")

# SQLite braucht einen Sonderparameter, damit dieselbe Connection ueber Threads geteilt
# werden kann (TestClient nutzt das). Postgres braucht den Parameter nicht.
connect_args: dict = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Basisklasse fuer alle ORM-Modelle."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
