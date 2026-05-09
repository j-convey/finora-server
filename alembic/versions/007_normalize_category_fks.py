"""Normalize category references: use category_id FK everywhere

Revision ID: 007_normalize_category_fks
Revises: 006_add_household_fks
Create Date: 2026-05-08 00:00:00.000000

Changes:
  - transactions.category (String) → category_id (Integer FK to categories.id)
  - transactions.account_id gets explicit FK to accounts.id
  - budgets.category (String) → category_id (Integer FK to categories.id)
  - Adds partial unique index on categories (name) WHERE household_id IS NULL
    to enforce uniqueness of system category names (NULLs are treated as
    distinct in standard unique constraints, so a partial index is required).

Backfill strategy (for fresh installs running all migrations in sequence):
  - Match existing category strings case-insensitively to category names.
  - Unmatched transactions fall back to 'Uncategorized'.

NOTE: Users must reset their database before running this migration if they
have existing data. The migration is safe for fresh DB installs only.
"""
from alembic import op
import sqlalchemy as sa


revision = "007_normalize_category_fks"
down_revision = "006_add_household_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Partial unique index for system categories ─────────────────────────
    # Standard unique constraints treat NULLs as distinct, so (household_id, name)
    # does NOT prevent duplicate system category names. This partial index fixes it.
    op.execute(
        "CREATE UNIQUE INDEX uix_categories_system_name ON categories (name) "
        "WHERE household_id IS NULL"
    )

    # ── 2. transactions.category → category_id ───────────────────────────────
    op.add_column(
        "transactions",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    # Backfill: case-insensitive match against system categories
    op.execute("""
        UPDATE transactions t
        SET category_id = c.id
        FROM categories c
        WHERE LOWER(c.name) = LOWER(t.category)
          AND c.household_id IS NULL
    """)
    # Remaining nulls → Uncategorized
    op.execute("""
        UPDATE transactions
        SET category_id = (
            SELECT id FROM categories
            WHERE LOWER(name) = 'uncategorized'
              AND household_id IS NULL
            LIMIT 1
        )
        WHERE category_id IS NULL
          AND category IS NOT NULL
    """)
    op.create_foreign_key(
        "fk_transactions_category_id", "transactions", "categories",
        ["category_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.drop_column("transactions", "category")

    # ── 3. transactions.account_id → FK to accounts ──────────────────────────
    op.create_foreign_key(
        "fk_transactions_account_id", "transactions", "accounts",
        ["account_id"], ["id"], ondelete="SET NULL"
    )

    # ── 4. budgets.category → category_id ───────────────────────────────────
    op.add_column(
        "budgets",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    # Backfill: case-insensitive match against system categories
    op.execute("""
        UPDATE budgets b
        SET category_id = c.id
        FROM categories c
        WHERE LOWER(c.name) = LOWER(b.category)
          AND c.household_id IS NULL
    """)
    # Fallback: any remaining nulls get the first available category
    op.execute("""
        UPDATE budgets
        SET category_id = (SELECT id FROM categories ORDER BY id LIMIT 1)
        WHERE category_id IS NULL
    """)

    # Drop old unique constraint on (household_id, category string)
    op.drop_constraint("uq_budgets_household_category", "budgets", type_="unique")
    # New unique constraint on (household_id, category_id)
    op.create_unique_constraint(
        "uq_budgets_household_category_id", "budgets", ["household_id", "category_id"]
    )
    op.create_foreign_key(
        "fk_budgets_category_id", "budgets", "categories",
        ["category_id"], ["id"]
    )
    op.create_index("ix_budgets_category_id", "budgets", ["category_id"])
    op.drop_column("budgets", "category")


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade not implemented. This migration converts string categories to "
        "relational IDs. Reversing requires manual data recovery."
    )
