"""Add reimbursement junction table and household_id to transactions

Revision ID: 009_add_reimbursements
Revises: 008_add_split_transactions
Create Date: 2026-05-09 00:00:00.000000

Changes:
  - transactions.household_id (Integer FK → households.id, indexed)
      Enables direct household-scoped queries and tenant isolation checks
      without requiring a join through accounts every time.
      Backfilled from accounts.household_id for existing rows.
  
  - transaction_reimbursements (new junction table)
      Links an expense transaction to an income transaction with an amount.
      Supports partial reimbursements, prevents double-counting in reports,
      and cleans up automatically (ON DELETE CASCADE) when either side is deleted.
      
      Indexes:
        - idx_reimb_expense_txn  (expense_transaction_id)
        - idx_reimb_income_txn   (income_transaction_id)
        - idx_reimb_created_at   (created_at)
      
      Constraints:
        - uq_expense_income UNIQUE (expense_transaction_id, income_transaction_id)
        - ck_reimb_amount_positive CHECK (amount > 0)
"""
from alembic import op
import sqlalchemy as sa


revision = "009_add_reimbursements"
down_revision = "008_add_split_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add household_id to transactions ──────────────────────────────────
    op.add_column(
        "transactions",
        sa.Column("household_id", sa.Integer(), nullable=True),
    )
    # Backfill from the linked account's household_id.
    # Transactions with no account_id (edge case) will remain NULL.
    op.execute(
        """
        UPDATE transactions t
        SET household_id = a.household_id
        FROM accounts a
        WHERE t.account_id = a.id
        """
    )
    op.create_foreign_key(
        "fk_transactions_household_id",
        "transactions",
        "households",
        ["household_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_household_id", "transactions", ["household_id"])

    # ── 2. Create transaction_reimbursements junction table ──────────────────
    op.create_table(
        "transaction_reimbursements",
        sa.Column(
            "id",
            sa.String(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "expense_transaction_id",
            sa.String(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "income_transaction_id",
            sa.String(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Stored as Numeric(19,4) to match transactions.amount exactly.
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # FK to users.id (Integer PK in this schema)
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "expense_transaction_id",
            "income_transaction_id",
            name="uq_expense_income",
        ),
        sa.CheckConstraint("amount > 0", name="ck_reimb_amount_positive"),
    )

    op.create_index(
        "idx_reimb_expense_txn",
        "transaction_reimbursements",
        ["expense_transaction_id"],
    )
    op.create_index(
        "idx_reimb_income_txn",
        "transaction_reimbursements",
        ["income_transaction_id"],
    )
    op.create_index(
        "idx_reimb_created_at",
        "transaction_reimbursements",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_reimb_created_at", table_name="transaction_reimbursements")
    op.drop_index("idx_reimb_income_txn", table_name="transaction_reimbursements")
    op.drop_index("idx_reimb_expense_txn", table_name="transaction_reimbursements")
    op.drop_table("transaction_reimbursements")

    op.drop_index("ix_transactions_household_id", table_name="transactions")
    op.drop_constraint("fk_transactions_household_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "household_id")
