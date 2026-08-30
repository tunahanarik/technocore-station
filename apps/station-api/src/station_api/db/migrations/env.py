"""Alembic environment.

The engine is built through ``station_api.db.engine`` so the WAL and
foreign-key PRAGMAs are applied on connect, before Alembic opens its
migration transaction.

The version table is ``schema_migrations`` rather than Alembic's default
``alembic_version`` (IMP-102).
"""

from __future__ import annotations

from alembic import context

from station_api.db.engine import create_engine_from_url
from station_api.db.models import VERSION_TABLE_NAME, Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE_NAME,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if url is None:  # pragma: no cover - misconfiguration guard
        raise RuntimeError("sqlalchemy.url is not configured")

    connectable = create_engine_from_url(url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE_NAME,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
