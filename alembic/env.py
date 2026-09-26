"""Alembic environment. The URL follows SERAH_DB_PATH when it is set."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from serah.config import get_settings
from serah.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", "sqlite:///" + str(get_settings().resolved_db_path()))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
