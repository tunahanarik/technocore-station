"""SI-39 .. SI-43 - WAL, foreign keys, deterministic and idempotent migrations.

ADR-0010 6 adds the two cases that were never covered. Everything here used
to run against **empty** databases: idempotence, a repeated launch, the shape
of the revision chain. Nothing upgraded a database that carried rows, and
nothing asked what an older build does when it opens a newer file - a search
for ``downgrade`` and ``unknown revision`` in this suite came back empty. An
installation root without a version number in it (ADR-0010 6 refuses a
``current`` junction, which is what H2's reparse-point defence exists to
reject) means upgrade-in-place is the only path there is, so both are tested
here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, text
from station_api.db.engine import create_database_engine
from station_api.db.migrations_runner import (
    SchemaAheadError,
    build_alembic_config,
    current_revision,
    initialise_database,
    known_revisions,
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


#: The revision Package F shipped, and the one an upgrade has to arrive at.
#: Written out rather than derived, for ``CURRENT_SCHEMA_STAGE``'s reason: a
#: constant that read the head off the script directory would agree with
#: whatever the script directory happened to say.
OLDER_RELEASE_REVISION = "0007"
CURRENT_MIGRATION_HEAD = "0009"


def test_an_upgrade_from_an_older_release_keeps_the_rows_it_found(
    tmp_path: Path,
) -> None:
    """ADR-0010 6. A populated ``0007`` database reaches ``0009`` intact.

    The gap this closes is specific. Every migration test before Package I
    ran against an empty file, so "additive only" was checked as a property
    of the *schema* and never once as a property of somebody's data. An
    installation root with no version in its name means the only upgrade path
    is in place, over the user's own rows, and that is what is exercised
    here: an identity, a task and an application-metadata row are written at
    ``0007`` and read back after the upgrade, value by value.
    """
    db_path = tmp_path / "populated.sqlite3"
    command.upgrade(build_alembic_config(db_path), OLDER_RELEASE_REVISION)

    engine = create_database_engine(db_path)
    moment = datetime(2026, 9, 5, 12, 0, tzinfo=UTC).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO identity (id, did, public_key, fingerprint, label, "
                "status, active_slot, created_at) VALUES (:id, :did, :public_key, "
                ":fingerprint, :label, :status, :slot, :created_at)"
            ),
            {
                "id": "id-0001",
                "did": "did:example:TEST-ONLY",
                "public_key": "11",
                "fingerprint": "22",
                "label": "TEST-ONLY",
                "status": "active",
                "slot": 1,
                "created_at": moment,
            },
        )
        connection.execute(
            text(
                "INSERT INTO task_record (id, module_id, source_id, "
                "content_sha256, source_version_id, title, state, detail, "
                "created_at, updated_at) VALUES (:id, :module_id, :source_id, "
                ":content, :version, :title, :state, '', :created_at, :updated_at)"
            ),
            {
                "id": "task-0001",
                "module_id": "identity_local_only",
                "source_id": "src-1",
                "content": "ab",
                "version": "v1",
                "title": "TEST-ONLY gorev",
                "state": "draft",
                "created_at": moment,
                "updated_at": moment,
            },
        )
        connection.execute(
            text(
                "INSERT INTO app_metadata (key, value, updated_at) "
                "VALUES ('initialized_at', :value, :updated_at)"
            ),
            {"value": moment, "updated_at": moment},
        )
    assert current_revision(engine) == OLDER_RELEASE_REVISION
    engine.dispose()

    run_migrations(db_path)

    engine = create_database_engine(db_path)
    with engine.connect() as connection:
        identity = connection.exec_driver_sql(
            "SELECT did, fingerprint, status, active_slot FROM identity"
        ).all()
        task = connection.exec_driver_sql(
            "SELECT id, module_id, title, state FROM task_record"
        ).all()
        metadata = connection.exec_driver_sql(
            "SELECT value FROM app_metadata WHERE key = 'initialized_at'"
        ).scalar()
    revision = current_revision(engine)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert revision == CURRENT_MIGRATION_HEAD
    assert identity == [("did:example:TEST-ONLY", "22", "active", 1)]
    assert task == [("task-0001", "identity_local_only", "TEST-ONLY gorev", "draft")]
    assert metadata == moment
    # The tables the two later migrations add are there, and the ones that
    # were carrying rows are still there rather than recreated.
    assert {"identity", "task_record", "app_metadata"} <= tables
    assert "agent_run" in tables or "agent_activity" in tables


def test_a_database_from_a_newer_build_is_refused_in_words(tmp_path: Path) -> None:
    """ADR-0010 6, the other direction, which had no test at all.

    The forward-compatibility question was never asked before Package I. The
    honest answer has to be a refusal - this build has no idea what a
    revision it does not carry did to the schema - and the refusal has to be
    legible: without the guard the failure was Alembic's own
    ``Can't locate revision`` raised from inside ``upgrade``, which is a
    crash rather than a sentence, and one step away from the genuinely bad
    outcome of an old build running its ORM against a schema that moved.

    The message is asserted for what it must **not** say as well: nothing
    here suggests deleting anything (ADR-0010 5).
    """
    db_path = tmp_path / "from-the-future.sqlite3"
    run_migrations(db_path)

    future = "0099_written_by_a_newer_station"
    assert future not in known_revisions()

    engine = create_database_engine(db_path)
    with engine.begin() as connection:
        connection.execute(
            # The table name is a module constant and the value is bound, so
            # nothing here is built from anything a test could not see.
            text(f"UPDATE {VERSION_TABLE_NAME} SET version_num = :version"),  # noqa: S608
            {"version": future},
        )
    engine.dispose()

    with pytest.raises(SchemaAheadError) as caught:
        run_migrations(db_path)

    message = str(caught.value)
    assert future in message
    assert "daha yeni" in message
    assert "dokunulmadi" in message
    assert "silinmedi" in message

    # And the data really was left alone: the stamp is untouched.
    engine = create_database_engine(db_path)
    assert current_revision(engine) == future
    engine.dispose()


def test_a_database_at_a_known_revision_is_not_mistaken_for_a_newer_one(
    tmp_path: Path,
) -> None:
    """The allow side of the same guard.

    A guard that refused everything would be a guard nobody could keep, and a
    fresh file has no stamp at all - which is not "ahead", it is "empty".
    """
    fresh = tmp_path / "fresh.sqlite3"
    run_migrations(fresh)
    run_migrations(fresh)

    older = tmp_path / "older.sqlite3"
    command.upgrade(build_alembic_config(older), OLDER_RELEASE_REVISION)
    run_migrations(older)

    engine = create_database_engine(older)
    assert current_revision(engine) == CURRENT_MIGRATION_HEAD
    engine.dispose()

    assert OLDER_RELEASE_REVISION in known_revisions()
    assert CURRENT_MIGRATION_HEAD in known_revisions()


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
