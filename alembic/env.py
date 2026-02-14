"""
alembic.env

Alembic migration environment configuration.

Responsibilities:
- Provide metadata discovery for autogeneration.
- Configure offline/online migration execution.

Notes:
- This module is executed by Alembic, not imported by the FastAPI runtime.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from uca_orchestrator.db.base import Base
from uca_orchestrator.db import models  # noqa: F401  # ensure models are registered on Base.metadata
from uca_orchestrator.settings import Settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    # Prefer explicit env var for migrations
    if "UCA_DATABASE_URL" in os.environ:
        return os.environ["UCA_DATABASE_URL"]
    return Settings().database_url


def run_migrations_offline() -> None:
    # Offline: emit SQL scripts without a DB connection.
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Online: run migrations against a live DB connection.
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


# --- Module Notes -----------------------------------------------------------
# Keep this file aligned with SQLAlchemy metadata definitions in `uca_orchestrator.db.models`.

