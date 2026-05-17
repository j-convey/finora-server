"""Alembic environment configuration."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from sqlalchemy import text
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

    # Check for target schema in -x args (passed by apply_migrations.py)
    x_args = context.get_x_argument(as_dictionary=True)
    tenant_schema = x_args.get("tenant_schema")

    with connectable.connect() as connection:
        # If tenant_schema is provided, use schema_translate_map
        # to reroute public table definitions to the new schema
        configure_kwargs = {
            "connection": connection,
            "target_metadata": target_metadata,
        }

        if tenant_schema:
            # We must also ensure the alembic_version table is created in the correct schema
            configure_kwargs["version_table_schema"] = tenant_schema
            configure_kwargs["include_schemas"] = True

            # Translate metadata schema None (default) to tenant_schema
            connection = connection.execution_options(
                schema_translate_map={None: tenant_schema}
            )

            # Since execution_options returns a cloned connection, update our dict
            configure_kwargs["connection"] = connection

            # Ensure the schema actually exists before we try to migrate it
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {tenant_schema}"))
            connection.commit()

        context.configure(**configure_kwargs)

        with context.begin_transaction():
            if tenant_schema:
                # Explicitly set search path for safety
                context.execute(f"SET search_path TO {tenant_schema}")

            context.run_migrations()

            if tenant_schema:
                context.execute("SET search_path TO public")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
