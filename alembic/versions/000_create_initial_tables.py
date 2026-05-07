"""Create initial database schema (genesis migration)

Revision ID: 000_create_initial_tables
Revises: 
Create Date: 2026-05-06 00:00:00.000000

Creates the base tables that were originally bootstrapped via
SQLAlchemy's create_all(). Subsequent migrations (001+) alter these
tables incrementally.
"""
from alembic import op
import sqlalchemy as sa


revision = "000_create_initial_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="checking"),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("available_balance", sa.Numeric(19, 4), nullable=True),
        sa.Column("institution_name", sa.String(), nullable=True),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("original_description", sa.String(), nullable=True),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("provider_transaction_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False, server_default="Uncategorized"),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactions_provider_transaction_id", "transactions", ["provider_transaction_id"])

    op.create_table(
        "budgets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("allocated", sa.Numeric(19, 4), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("category", name="uq_budgets_category"),
    )
    op.create_index("ix_budgets_category", "budgets", ["category"])

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("net_worth", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_assets", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_liabilities", sa.Numeric(19, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_user_snapshot_date"),
    )
    op.create_index("ix_account_snapshots_id", "account_snapshots", ["id"])
    op.create_index("ix_account_snapshots_user_id", "account_snapshots", ["user_id"])
    op.create_index("ix_account_snapshots_snapshot_date", "account_snapshots", ["snapshot_date"])

    op.create_table(
        "simplefin_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("access_url_encrypted", sa.Text(), nullable=False),
        sa.Column("institutions", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("simplefin_config")
    op.drop_index("ix_account_snapshots_snapshot_date", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_user_id", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_id", table_name="account_snapshots")
    op.drop_table("account_snapshots")
    op.drop_index("ix_budgets_category", table_name="budgets")
    op.drop_table("budgets")
    op.drop_index("ix_transactions_provider_transaction_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
