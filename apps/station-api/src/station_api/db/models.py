"""ORM models.

Stage 1 defines infrastructure tables only:

``schema_migrations``  the Alembic version ledger (created and owned by
                       Alembic, renamed from its default; not modelled here)
``app_metadata``       small key/value facts about this installation

There is no ``Identity``, ``SecretMetadata`` or ``Evidence`` table yet, and by
construction no column anywhere holds a seed or private key (SI-43).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Alembic version table name. Kept as ``schema_migrations`` to match the
#: project brief rather than Alembic's ``alembic_version`` default (IMP-102).
VERSION_TABLE_NAME = "schema_migrations"


class Base(DeclarativeBase):
    pass


class AppMetadata(Base):
    """Key/value facts about this installation. Never holds a secret."""

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AppMetadata(key={self.key!r})"
