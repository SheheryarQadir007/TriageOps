"""SQLite / SQLAlchemy engine and session management.

The database is intentionally wrapped in a small class so that tests and
multiple app instances can use isolated databases without module-level state.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self._ensure_sqlite_directory(url)

        connect_args: dict[str, object] = {}
        if _is_sqlite(url):
            connect_args["check_same_thread"] = False

        self.engine: Engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            future=True,
        )
        if _is_sqlite(url):
            self._configure_sqlite()

        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @staticmethod
    def _ensure_sqlite_directory(url: str) -> None:
        parsed = make_url(url)
        if not parsed.drivername.startswith("sqlite"):
            return
        database = parsed.database
        if not database or database == ":memory:":
            return
        parent = Path(database).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)

    def _configure_sqlite(self) -> None:
        """Enable WAL + sane concurrency defaults for a single-file SQLite DB."""

        is_memory = make_url(self.url).database in (None, "", ":memory:")

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                if not is_memory:
                    cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

    def create_all(self) -> None:
        # Import for side effects: registers every model on Base.metadata.
        from app import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    database: Database = request.app.state.db
    with database.session() as session:
        yield session
