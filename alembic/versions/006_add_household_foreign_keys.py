"""Add household_id foreign keys to orphaned tables

Revision ID: 006_add_household_fks
Revises: 005_add_auth_and_households
Create Date: 2026-05-08 00:00:00.000000

Changes:
  - Adds household_id to accounts table (tie to household, enable multi-tenant queries)
  - Adds nullable household_id to categories (allows system + custom categories)
  - Adds household_id to budgets (tie budgets to specific household)
  - Migrates simplefin_config.id from singleton to per-household (household_id)
  
  This ensures proper multi-tenant data isolation and prevents orphaned records.
"""
from alembic import op
import sqlalchemy as sa


revision = "006_add_household_fks"
down_revision = "005_add_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. accounts: Add household_id ────────────────────────────────────────
    op.add_column("accounts", sa.Column("household_id", sa.Integer(), nullable=True))
    # Backfill: assume all existing accounts belong to household 1
    op.execute("UPDATE accounts SET household_id = 1")
    op.alter_column("accounts", "household_id", nullable=False)
    op.create_foreign_key(
        "fk_accounts_household_id", "accounts", "households",
        ["household_id"], ["id"]
    )
    op.create_index("ix_accounts_household_id", "accounts", ["household_id"])

    # ── 2. categories: Add nullable household_id ─────────────────────────────
    # NULL household_id = system category (shared)
    # NOT NULL household_id = custom category (household-specific)
    op.add_column("categories", sa.Column("household_id", sa.Integer(), nullable=True))
    # Remove unique constraint on name (allows same name across households)
    op.drop_constraint("uq_categories_name", "categories", type_="unique")
    # Create new unique constraint: (household_id, name)
    # This allows same category name in different households but prevents duplicates within a household
    op.create_unique_constraint(
        "uq_categories_household_name",
        "categories",
        ["household_id", "name"]
    )
    op.create_foreign_key(
        "fk_categories_household_id", "categories", "households",
        ["household_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_categories_household_id", "categories", ["household_id"])
    # Keep system categories with NULL household_id (they are not tied to any household)

    # ── 3. budgets: Add household_id ─────────────────────────────────────────
    op.add_column("budgets", sa.Column("household_id", sa.Integer(), nullable=True))
    # Backfill: assume all existing budgets belong to household 1
    op.execute("UPDATE budgets SET household_id = 1")
    op.alter_column("budgets", "household_id", nullable=False)
    # Remove old unique constraint on category (now allows same category in different households)
    op.drop_constraint("uq_budgets_category", "budgets", type_="unique")
    # Create new unique constraint: (household_id, category)
    op.create_unique_constraint(
        "uq_budgets_household_category",
        "budgets",
        ["household_id", "category"]
    )
    op.create_foreign_key(
        "fk_budgets_household_id", "budgets", "households",
        ["household_id"], ["id"]
    )
    op.create_index("ix_budgets_household_id", "budgets", ["household_id"])

    # ── 4. simplefin_config: Convert from singleton to per-household ─────────
    # Drop the old id=1 singleton row
    op.execute("DELETE FROM simplefin_config")
    # Remove old primary key
    op.drop_constraint("simplefin_config_pkey", "simplefin_config", type_="primary")
    # Drop old id column
    op.drop_column("simplefin_config", "id")
    # Add household_id as primary key (one config per household)
    op.add_column("simplefin_config", sa.Column("household_id", sa.Integer(), primary_key=True))
    op.create_foreign_key(
        "fk_simplefin_config_household_id", "simplefin_config", "households",
        ["household_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    # Note: Downgrade is complex due to the singleton → per-household migration.
    # For now, leave downgrade unimplemented or provide manual steps.
    # (In production, you'd typically create a full reversal, but this is a breaking change.)
    raise NotImplementedError(
        "Downgrade not implemented. This migration converts singleton simplefin_config "
        "to per-household. Reversing would require manual data recovery."
    )
