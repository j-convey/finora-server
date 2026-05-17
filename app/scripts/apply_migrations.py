import sys
import argparse
from alembic.config import Config
from alembic import command
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("finora.apply_migrations")

def apply_migrations(demo_only: bool = False, main_only: bool = False):
    """
    Run Alembic migrations on public schema, then on demo schema.
    Alembic natively runs against the engine connection. To target a different schema,
    we need to ensure the `version_table_schema` is set correctly and the
    `search_path` or explicit schema references are used.

    A simpler approach for this isolated environment is to run the alembic command,
    but use an event listener in `alembic/env.py` or modify the connection string.
    However, the easiest way to manage this without complex alembic.ini overrides
    is to explicitly set the schema translate map in `alembic/env.py`.
    """
    # Create Alembic configuration object
    alembic_cfg = Config("alembic.ini")

    try:
        if not demo_only:
            logger.info("Running migrations for main (public) schema...")
            # Run upgrade head for the default (public) schema
            command.upgrade(alembic_cfg, "head")
            logger.info("Main schema migrations complete.")

        if not main_only:
            schema_name = settings.DEMO_SCHEMA
            logger.info(f"Running migrations for demo schema ('{schema_name}')...")

            # We pass the schema name as an 'x' argument to alembic
            # so `alembic/env.py` can intercept it.
            alembic_cfg.cmd_opts = argparse.Namespace(x=[f"tenant_schema={schema_name}"])
            command.upgrade(alembic_cfg, "head")
            logger.info("Demo schema migrations complete.")

    except Exception as e:
        logger.exception("Failed to run migrations.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply migrations to main and demo schemas.")
    parser.add_argument("--demo-only", action="store_true", help="Only migrate the demo schema.")
    parser.add_argument("--main-only", action="store_true", help="Only migrate the main schema.")
    args = parser.parse_args()

    apply_migrations(demo_only=args.demo_only, main_only=args.main_only)
