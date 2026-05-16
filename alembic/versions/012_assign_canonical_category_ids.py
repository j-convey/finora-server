"""Assign canonical stable IDs to system categories.

Revision ID: 012_assign_canonical_category_ids
Revises: 011_restructure_categories
Create Date: 2026-05-15 00:00:00.000000

Why:
  System categories are a fixed, curated list. Assigning stable IDs means
  Flutter clients (and any other consumer) can cache the category list
  indefinitely and reference category IDs without re-fetching.

  The canonical ID for each system category is: sort_order + 1
  (sort_order was set sequentially 0–142 in migration 011).

  This migration is safe to re-run; if the IDs are already canonical
  (fresh DB that ran migration 011 first), the UPDATE is a no-op.

What it does:
  1. Temporarily drops FK constraints on transactions.category_id and
     budgets.category_id (both will be re-added at the end).
  2. Shifts custom-category IDs that fall in the range 1–143 out of the
     way (adds 10 000), to avoid PK conflicts during the re-keying.
  3. Rewrites all FK references in transactions and budgets using the
     sort_order → new_id mapping.
  4. Rewrites the category PKs themselves (two-phase via negatives to
     avoid mid-update uniqueness violations).
  5. Restores any shifted custom categories.
  6. Recreates the FK constraints.
  7. Resets the categories_id_seq to 143 so new custom categories start
     from 144 and never collide with system IDs.
"""
from alembic import op
import sqlalchemy as sa

revision = "012_assign_canonical_category_ids"
down_revision = "011_restructure_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Drop FK constraints so we can freely mutate PKs/FKs.
    # ------------------------------------------------------------------
    conn.execute(sa.text(
        "ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_category_id_fkey"
    ))
    conn.execute(sa.text(
        "ALTER TABLE budgets DROP CONSTRAINT IF EXISTS budgets_category_id_fkey"
    ))

    # ------------------------------------------------------------------
    # 2. Move custom categories (household_id IS NOT NULL) whose current
    #    ID falls in 1–143 out of the way to avoid PK conflicts.
    #    Their FK references in transactions/budgets are handled below.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE categories
        SET id = id + 10000
        WHERE household_id IS NOT NULL
          AND id BETWEEN 1 AND 143
    """))

    # ------------------------------------------------------------------
    # 3. Rewrite FK references in transactions to point at canonical IDs.
    #    We join through the categories table using the current (pre-remap)
    #    id and compute the desired id as sort_order + 1.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE transactions t
        SET category_id = c.sort_order + 1
        FROM categories c
        WHERE t.category_id = c.id
          AND c.household_id IS NULL
    """))

    # ------------------------------------------------------------------
    # 4. Rewrite FK references in budgets similarly.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE budgets b
        SET category_id = c.sort_order + 1
        FROM categories c
        WHERE b.category_id = c.id
          AND c.household_id IS NULL
    """))

    # ------------------------------------------------------------------
    # 5. Rewrite the system category PKs themselves.
    #    Phase A: set to negative to avoid mid-update uniqueness errors
    #             (e.g. new_id of row A == old_id of row B).
    #    Phase B: negate back to positive.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE categories
        SET id = -(sort_order + 1)
        WHERE household_id IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE categories
        SET id = -id
        WHERE id < 0
    """))

    # ------------------------------------------------------------------
    # 6. Restore any custom categories that were temporarily shifted.
    #    Their FK references were not changed — they still point to the
    #    original IDs, which are now restored here.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE categories
        SET id = id - 10000
        WHERE household_id IS NOT NULL
          AND id > 10000
    """))

    # ------------------------------------------------------------------
    # 7. Recreate FK constraints.
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        ALTER TABLE transactions
        ADD CONSTRAINT transactions_category_id_fkey
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
    """))
    conn.execute(sa.text("""
        ALTER TABLE budgets
        ADD CONSTRAINT budgets_category_id_fkey
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
    """))

    # ------------------------------------------------------------------
    # 8. Reset the sequence so new custom categories start from 144.
    #    setval(seq, 143) means the NEXT nextval() call returns 144.
    # ------------------------------------------------------------------
    conn.execute(sa.text("SELECT setval('categories_id_seq', 143)"))


def downgrade() -> None:
    # Reversing PK changes is destructive and not reliably possible once
    # custom categories or transactions have been added post-upgrade.
    # The safest downgrade is a no-op with a warning — run migration 011
    # fresh if a full rollback is needed.
    pass
