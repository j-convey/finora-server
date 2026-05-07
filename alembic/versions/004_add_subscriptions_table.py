"""Add subscriptions table and transaction subscription link

Revision ID: 004_add_subscriptions_table
Revises: 003_add_categories
Create Date: 2026-05-06 00:00:03.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "004_add_subscriptions_table"
down_revision = "003_add_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("expected_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("min_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("max_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("recurrence_interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recurrence_unit", sa.String(), nullable=False, server_default="month"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("auto_link_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("matching_notes", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("recurrence_interval > 0", name="ck_subscriptions_recurrence_interval_positive"),
        sa.CheckConstraint(
            "end_date IS NULL OR status <> 'active'",
            name="ck_subscriptions_end_date_not_active",
        ),
        sa.CheckConstraint(
            "min_amount IS NULL OR max_amount IS NULL OR min_amount <= max_amount",
            name="ck_subscriptions_amount_range_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'canceled')",
            name="ck_subscriptions_status_valid",
        ),
        sa.CheckConstraint(
            "recurrence_unit IN ('day', 'week', 'month', 'year')",
            name="ck_subscriptions_recurrence_unit_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_name", "subscriptions", ["name"])
    op.create_index("ix_subscriptions_merchant_name", "subscriptions", ["merchant_name"])
    op.create_index("ix_subscriptions_category", "subscriptions", ["category"])
    op.create_index("ix_subscriptions_next_due_date", "subscriptions", ["next_due_date"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.add_column("transactions", sa.Column("subscription_id", sa.String(), nullable=True))
    op.create_index("ix_transactions_subscription_id", "transactions", ["subscription_id"])
    op.create_foreign_key(
        "fk_transactions_subscription_id",
        "transactions",
        "subscriptions",
        ["subscription_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_subscriptions_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_subscriptions_updated_at
        BEFORE UPDATE ON subscriptions
        FOR EACH ROW
        EXECUTE FUNCTION set_subscriptions_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;")
    op.execute("DROP FUNCTION IF EXISTS set_subscriptions_updated_at;")

    op.drop_constraint("fk_transactions_subscription_id", "transactions", type_="foreignkey")
    op.drop_index("ix_transactions_subscription_id", table_name="transactions")
    op.drop_column("transactions", "subscription_id")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_next_due_date", table_name="subscriptions")
    op.drop_index("ix_subscriptions_category", table_name="subscriptions")
    op.drop_index("ix_subscriptions_merchant_name", table_name="subscriptions")
    op.drop_index("ix_subscriptions_name", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

