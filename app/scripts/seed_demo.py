import asyncio
import json
import argparse
import sys
from pathlib import Path
from sqlalchemy import text
from app.core.database import AsyncSessionLocal, engine
from app.core.config import settings
from app.infrastructure.models.account import Account
from app.infrastructure.models.subscription import Subscription
from app.infrastructure.models.transaction import Transaction
from app.infrastructure.models.budget import Budget
from app.infrastructure.models.account_snapshot import AccountSnapshot
from app.infrastructure.models.simplefin_config import SimplefinConfig
from app.core.logging import get_logger

logger = get_logger("finora.seed_demo")

async def seed_demo(force: bool = False):
    schema_name = settings.DEMO_SCHEMA
    seed_file_path = Path(__file__).parent.parent / "data" / "demo_seed.json"

    if not seed_file_path.exists():
        logger.error(f"Seed file not found at {seed_file_path}")
        sys.exit(1)

    with open(seed_file_path, "r") as f:
        try:
            seed_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in seed file: {e}")
            sys.exit(1)

    async with AsyncSessionLocal() as session:
        try:
            if force:
                logger.info(f"Force flag provided. Recreating schema '{schema_name}'.")
                # Clean slate
                await session.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
                await session.execute(text(f"CREATE SCHEMA {schema_name}"))
                await session.commit()

                logger.info(f"Schema '{schema_name}' recreated. Re-running migrations...")
                import app.scripts.apply_migrations as apply_migrations
                # Run migrations asynchronously via threads or simply by importing and calling since we just dropped it
                apply_migrations.apply_migrations(demo_only=True)

            # Ensure we are operating on the demo schema
            await session.execute(text(f"SET search_path TO {schema_name}"))

            logger.info(f"Truncating existing data in '{schema_name}'.")
            tables = ["account_snapshots", "transactions", "subscriptions", "accounts", "budgets", "categories", "simplefin_config"]
            for table in tables:
                # Use a savepoint so that a failing TRUNCATE doesn't abort the entire transaction
                async with session.begin_nested():
                    try:
                        await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    except Exception as e:
                        logger.warning(f"Could not truncate {table}: {e}")
                        # Sub-transaction automatically rolls back, outer transaction remains valid

            # Load Data
            logger.info("Loading seed data...")

            for account_data in seed_data.get("accounts", []):
                session.add(Account(**account_data))

            for sub_data in seed_data.get("subscriptions", []):
                session.add(Subscription(**sub_data))

            for txn_data in seed_data.get("transactions", []):
                session.add(Transaction(**txn_data))

            for budget_data in seed_data.get("budgets", []):
                session.add(Budget(**budget_data))

            for snapshot_data in seed_data.get("account_snapshots", []):
                session.add(AccountSnapshot(**snapshot_data))

            if seed_data.get("simplefin_config"):
                session.add(SimplefinConfig(**seed_data["simplefin_config"]))

            await session.commit()
            logger.info(f"Successfully seeded '{schema_name}' schema.")

        except Exception as e:
            await session.rollback()
            logger.exception(f"Failed to seed demo database: {e}")
            sys.exit(1)
        finally:
            # Reset search path
            await session.execute(text("SET search_path TO public"))
            await session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the demo schema with sample data.")
    parser.add_argument("--force", action="store_true", help="Drop and recreate the demo schema before seeding.")
    args = parser.parse_args()

    asyncio.run(seed_demo(force=args.force))
