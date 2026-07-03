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

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bank_workflow.db")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

# SQLite braucht einen Sonderparameter, damit dieselbe Connection ueber Threads
# geteilt werden kann (TestClient + uvicorn-Worker nutzen das).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
    future=True,
)


if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
        """PRAGMAs, die SQLite pro Connection NICHT per Default setzt.

        - foreign_keys=ON  : sonst werden FK-/ON-DELETE-Constraints ignoriert
                             (Waisen-Datensaetze, RESTRICT ohne Wirkung).
        - journal_mode=WAL : Reader blockieren Writer nicht und umgekehrt.
        - busy_timeout     : statt sofortigem „database is locked" bis 5 s warten
                             (Request-Threads + APScheduler-Thread schreiben parallel).
        - synchronous=NORMAL: mit WAL sicher und deutlich schneller als FULL.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Basisklasse fuer alle ORM-Modelle."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request.

    Bei einer Exception im Request-Handler wird explizit zurueckgerollt, bevor
    die Session geschlossen wird — macht das Transaktionsverhalten sichtbar und
    verhindert, dass eine teil-geflushte Transaktion an die naechste
    wiederverwendete Connection durchschlaegt.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
