"""Programmatic Alembic driver.

Migrations run on every start. ``upgrade head`` is a no-op once the database
is current, which is what makes repeated launches safe (SI-41). Ordering is
the ``down_revision`` chain, so it is deterministic and cannot depend on
filesystem iteration order (SI-42).
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

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def build_alembic_config(db_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url(db_path))
    return config


def run_migrations(db_path: Path) -> None:
    """Bring the database at ``db_path`` up to the latest revision."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
