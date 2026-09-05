"""Programmatic Alembic driver.

Migrations run on every start. ``upgrade head`` is a no-op once the database
is current, which is what makes repeated launches safe (SI-41). Ordering is
the ``down_revision`` chain, so it is deterministic and cannot depend on
filesystem iteration order (SI-42).

Two things here are ADR-0010's, not Stage 1's.

**The script location is asked for rather than counted to.** Alembic reads
``env.py`` and every ``versions/*.py`` **as files**; ``__file__`` arithmetic
finds them in a checkout and in a wheel and finds nothing at all inside a
frozen bundle, where the modules live in an archive and the loader
synthesises the path. :mod:`station_api.resources` answers the question for
all three (ADR-0010 1).

**A database from a newer build is refused in words.** Downgrade was never
tested and forward compatibility was never tested either (ADR-0010 6): an
older Station opening a newer file used to reach Alembic's own
``Can't locate revision`` deep inside ``upgrade``. That is a refusal, but not
one a user can act on, and the failure it is one step away from - an older
build running happily against a schema it does not understand - is silent
corruption. So the revision is checked against this build's own revision map
first, and the refusal is :class:`SchemaAheadError` with a sentence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, insert, select, update

from station_api.db.engine import create_database_engine, database_url
from station_api.db.models import VERSION_TABLE_NAME, AppMetadata
from station_api.resources import migrations_dir


class SchemaAheadError(RuntimeError):
    """The database names a schema revision this build does not carry.

    Almost always "you opened data written by a newer Station". Never
    upgraded past, never downgraded, never guessed at: this build stops and
    says which revision it does not know, because the alternative is running
    ORM models against columns that may have moved.
    """


def build_alembic_config(db_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    config.set_main_option("sqlalchemy.url", database_url(db_path))
    return config


def known_revisions() -> frozenset[str]:
    """Every revision this build carries, as identifiers."""
    return frozenset(script.revision for script in script_directory().walk_revisions())


def guard_against_a_newer_schema(db_path: Path) -> None:
    """Refuse, in words, a database stamped with a revision we do not have.

    A database that does not exist yet, or that carries no version table yet,
    is not ahead of anything - it is empty, and ``upgrade head`` is exactly
    what it needs. Only a *stamped* revision this build cannot find is the
    forward-compatibility case.
    """
    if not db_path.is_file():
        return

    engine = create_database_engine(db_path)
    try:
        revision = current_revision(engine)
    finally:
        engine.dispose()

    if revision is None or revision in known_revisions():
        return

    raise SchemaAheadError(
        "Bu veritabani, bu Station surumunun tanimadigi bir sema surumu ile "
        f"isaretlenmis ({revision}). Muhtemelen daha yeni bir Station "
        "tarafindan yazildi. Veriye dokunulmadi; guncel surumu kullanin. "
        "Veri dizininiz oldugu yerde duruyor ve silinmedi."
    )


def run_migrations(db_path: Path) -> None:
    """Bring the database at ``db_path`` up to the latest revision."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    guard_against_a_newer_schema(db_path)
    command.upgrade(build_alembic_config(db_path), "head")


def script_directory() -> ScriptDirectory:
    """Load the revision graph without touching a database."""
    return ScriptDirectory.from_config(build_alembic_config(Path("unused.sqlite3")))


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"version_table": VERSION_TABLE_NAME}
        )
        return context.get_current_revision()


def ensure_app_metadata(engine: Engine, *, stage: int) -> None:
    """Record non-secret facts about this installation.

    Kept out of the migration itself so migrations stay pure DDL and carry no
    timestamp that would differ between machines. Written as an upsert so a
    second launch updates rather than duplicates.
    """
    now = datetime.now(UTC)
    revision = current_revision(engine) or "unknown"

    with engine.begin() as connection:
        existing = {row[0] for row in connection.execute(select(AppMetadata.key)).all()}

        rows = {
            "application": "technocore-station",
            "schema_revision": revision,
            "stage": str(stage),
        }
        if "initialized_at" not in existing:
            rows["initialized_at"] = now.isoformat()

        for key, value in rows.items():
            if key in existing:
                connection.execute(
                    update(AppMetadata)
                    .where(AppMetadata.key == key)
                    .values(value=value, updated_at=now)
                )
            else:
                connection.execute(
                    insert(AppMetadata).values(key=key, value=value, updated_at=now)
                )


def initialise_database(db_path: Path, *, stage: int = 1) -> Engine:
    """Migrate, then open an engine for the application to use."""
    run_migrations(db_path)
    engine = create_database_engine(db_path)
    ensure_app_metadata(engine, stage=stage)
    return engine
