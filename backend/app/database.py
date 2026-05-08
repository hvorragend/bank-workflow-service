"""SQLAlchemy-2.0-Setup.

Die Anwendung nutzt SQLite als einziges DB-System. Die Datei liegt im
Container unter `/app/data/bank_workflow.db` (per Volume persistiert);
lokal ohne Container im Backend-Arbeitsverzeichnis.

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

# SQLite braucht einen Sonderparameter, damit dieselbe Connection ueber Threads
# geteilt werden kann (TestClient + uvicorn-Worker nutzen das).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
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
