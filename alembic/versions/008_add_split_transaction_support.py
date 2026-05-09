"""Add split transaction support to transactions table

Revision ID: 008_add_split_transaction_support
Revises: 007_normalize_category_fks
Create Date: 2026-05-08 00:00:00.000000

Changes:
  - transactions.is_split_parent  (Boolean, default false, indexed)
      True only on the "ghost" parent row created when a user splits a transaction.
      Budget / analytics queries MUST filter WHERE is_split_parent = FALSE to
      avoid double-counting the parent amount alongside its children.
  - transactions.parent_transaction_id  (Nullable FK → transactions.id, CASCADE)
      Set on every child split row. NULL on all normal and parent rows.
      Bank-reconciliation queries MUST filter WHERE parent_transaction_id IS NULL
      to see only the actual bank hits.
  - transactions.requires_user_review  (Boolean, default false, indexed)
      Set by the SimpleFIN sync when a split parent's amount changes (pending→posted
      amount drift). Prompts the client to let the user re-reconcile the split.
"""
from alembic import op
import sqlalchemy as sa


revision = "008_add_split_transactions"
down_revision = "007_normalize_category_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_split_parent — used by budget/analytics queries to ignore ghost parent rows
    op.add_column(
        "transactions",
        sa.Column(
            "is_split_parent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_transactions_is_split_parent", "transactions", ["is_split_parent"])

    # parent_transaction_id — links child splits back to their parent
    op.add_column(
        "transactions",
        sa.Column("parent_transaction_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_parent_id",
        "transactions",
        "transactions",
        ["parent_transaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_transactions_parent_transaction_id",
        "transactions",
        ["parent_transaction_id"],
    )

    # requires_user_review — set when SimpleFIN detects split-amount drift
    op.add_column(
        "transactions",
        sa.Column(
            "requires_user_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_transactions_requires_user_review",
        "transactions",
        ["requires_user_review"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_requires_user_review", table_name="transactions")
    op.drop_column("transactions", "requires_user_review")

    op.drop_index("ix_transactions_parent_transaction_id", table_name="transactions")
    op.drop_constraint("fk_transactions_parent_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "parent_transaction_id")

    op.drop_index("ix_transactions_is_split_parent", table_name="transactions")
    op.drop_column("transactions", "is_split_parent")
