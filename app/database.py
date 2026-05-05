"""SQLAlchemy 2.0 setup. SQLite for local development, PostgreSQL for production."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# In production: postgresql+psycopg://user:pw@host/db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./idv_workflow.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
