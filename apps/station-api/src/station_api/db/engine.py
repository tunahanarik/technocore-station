"""SQLite engine construction.

Both PRAGMAs are applied from the ``connect`` event, which fires on the raw
DBAPI connection before SQLAlchemy opens any transaction. That ordering
matters: ``PRAGMA journal_mode`` cannot change inside a transaction, so
setting it from a normal ``execute`` would silently fail (SI-39, SI-40).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event


def database_url(db_path: Path) -> str:
    """Build a SQLAlchemy URL for a filesystem path.

    ``as_posix`` keeps Windows drive paths usable in a URL, where a backslash
    would otherwise be read as an escape.
    """
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _apply_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_engine_from_url(url: str) -> Engine:
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _apply_pragmas)
    return engine


def create_database_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine_from_url(database_url(db_path))
