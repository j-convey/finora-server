"""Alembic environment configuration."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
# Interpret the config file for Python logging.
# Guard required because Python 3.12 fileConfig is strict about missing
# 'root' logger declarations in some Alembic-generated alembic.ini templates.
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except (ValueError, KeyError):
        pass  # logging config not critical — skip if malformed

# Alembic uses a synchronous engine, but the app URL uses the asyncpg
# async driver (postgresql+asyncpg://...). Strip the +asyncpg suffix so
# Alembic gets a plain psycopg2-compatible URL (postgresql://...).
_sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", _sync_url)

# Set target metadata for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
