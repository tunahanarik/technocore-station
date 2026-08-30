"""SI-39 .. SI-43 - WAL, foreign keys, deterministic and idempotent migrations."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect
from station_api.db.engine import create_database_engine
from station_api.db.migrations_runner import (
    current_revision,
    initialise_database,
    run_migrations,
    script_directory,
)
from station_api.db.models import VERSION_TABLE_NAME

pytestmark = pytest.mark.security

FORBIDDEN_COLUMN_FRAGMENTS = (
    "seed",
    "private",
    "secret",
    "mnemonic",
    "passphrase",
    "password",
)


def test_wal_journal_mode_enabled(engine: Engine) -> None:
    with engine.connect() as connection:
        mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert str(mode).lower() == "wal"


def test_foreign_keys_enabled(engine: Engine) -> None:
    with engine.connect() as connection:
        enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert int(enabled or 0) == 1


def test_foreign_keys_enabled_on_every_new_connection(engine: Engine) -> None:
    """A pool can hand out a fresh connection at any time."""
    for _ in range(3):
        with engine.connect() as connection:
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            assert int(enabled or 0) == 1


def test_infrastructure_tables_exist(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert VERSION_TABLE_NAME in tables
    assert "app_metadata" in tables


def test_version_table_is_named_schema_migrations(engine: Engine) -> None:
    """The brief names this table; Alembic's default would be alembic_version."""
    assert VERSION_TABLE_NAME == "schema_migrations"
    tables = set(inspect(engine).get_table_names())
    assert VERSION_TABLE_NAME in tables
    assert "alembic_version" not in tables


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    """Reopening the application must not fail or change the schema."""
    db_path = tmp_path / "idempotent.sqlite3"

    run_migrations(db_path)
    engine = create_database_engine(db_path)
    first_revision = current_revision(engine)
    first_tables = set(inspect(engine).get_table_names())
    engine.dispose()

    # Second run: must be a clean no-op.
    run_migrations(db_path)
    engine = create_database_engine(db_path)
    second_revision = current_revision(engine)
    second_tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert first_revision == second_revision
    assert first_tables == second_tables


def test_initialise_database_is_repeatable(tmp_path: Path) -> None:
    """The full startup path, run twice, as a relaunch would."""
    db_path = tmp_path / "relaunch.sqlite3"

    first = initialise_database(db_path, stage=1)
    first_revision = current_revision(first)
    first.dispose()

    second = initialise_database(db_path, stage=1)
    second_revision = current_revision(second)

    with second.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT key, value FROM app_metadata ORDER BY key"
        ).all()
    second.dispose()

    assert first_revision == second_revision
    keys = [str(row[0]) for row in rows]
    assert keys == sorted(set(keys)), "metadata rows must be upserted, not duplicated"
    assert "initialized_at" in keys


def test_migration_chain_is_deterministic() -> None:
    """One head and a linear chain: the order cannot depend on file listing."""
    script = script_directory()

    heads = script.get_heads()
    assert len(heads) == 1, f"expected a single head, found {heads}"

    revisions = list(script.walk_revisions())
    assert revisions, "at least one migration must exist"

    for revision in revisions:
        down = revision.down_revision
        assert down is None or isinstance(down, str), (
            f"revision {revision.revision} branches; the order would be ambiguous"
        )


def test_schema_has_no_secret_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    offenders: list[str] = []

    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in FORBIDDEN_COLUMN_FRAGMENTS):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"secret-shaped columns found: {offenders}"


def test_database_file_lives_under_the_configured_data_dir(
    engine: Engine, data_dir: Path
) -> None:
    assert engine is not None
    assert (data_dir / "station.sqlite3").is_file()


def test_no_seed_material_is_written_to_the_database(
    engine: Engine, data_dir: Path
) -> None:
    """Stage 1 stores nothing sensitive; this guards the next stage too."""
    assert engine is not None
    for path in data_dir.rglob("*.sqlite3*"):
        blob = path.read_bytes().lower()
        for fragment in (b"mnemonic", b"private_key", b"secret_seed"):
            assert fragment not in blob
