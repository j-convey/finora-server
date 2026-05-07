"""Add categories table and provider_category column on transactions

Revision ID: 003_add_categories_and_provider_category
Revises: 002_add_transaction_constraints
Create Date: 2026-05-06 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "003_add_categories"
down_revision = "002_add_transaction_constraints"
branch_labels = None
depends_on = None


_DEFAULT_CATEGORIES = [
    # Income
    "Paychecks",
    "Interest",
    "Business Income",
    "Other Income",
    # Gifts & Donations
    "Charity",
    "Gifts",
    # Auto & Transport
    "Auto Payment",
    "Public Transit",
    "Gas",
    "Auto Maintenance",
    "Parking & Tolls",
    "Taxi & Ride Shares",
    # Housing
    "Mortgage",
    "Rent",
    "Home Improvement",
    # Bills & Utilities
    "Garbage",
    "Water",
    "Gas & Electric",
    "Internet & Cable",
    "Phone",
    # Food & Dining
    "Groceries",
    "Restaurants & Bars",
    "Coffee Shops",
    # Travel & Lifestyle
    "Travel & Vacation",
    "Entertainment & Recreation",
    "Personal",
    "Pets",
    "Fun Money",
    # Shopping
    "Shopping",
    "Clothing",
    "Furniture & Housewares",
    "Electronics",
    # Children
    "Child Care",
    "Child Activities",
    # Education
    "Student Loans",
    "Education",
    # Health & Wellness
    "Medical",
    "Dentist",
    "Fitness",
    # Financial
    "Loan Repayment",
    "Financial & Legal Services",
    "Financial Fees",
    "Cash & ATM",
    "Insurance",
    "Taxes",
    # Other
    "Uncategorized",
    "Check",
    "Miscellaneous",
    # Business
    "Advertising & Promotion",
    "Business Utilities & Communication",
    "Employee Wages & Contract Labor",
    "Business Travel & Meals",
    "Business Auto Expenses",
    "Business Insurance",
    "Office Supplies & Expenses",
    "Office Rent",
    "Postage & Shipping",
    # Transfers
    "Transfer",
    "Credit Card Payment",
    "Balance Adjustments",
]


def upgrade() -> None:
    # 1. categories table
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index("ix_categories_name", "categories", ["name"])

    # Seed system defaults
    op.bulk_insert(
        categories,
        [
            {"name": name, "is_system": True, "sort_order": idx}
            for idx, name in enumerate(_DEFAULT_CATEGORIES)
        ],
    )

    # 2. provider_category column on transactions
    op.add_column(
        "transactions",
        sa.Column("provider_category", sa.String(), nullable=True),
    )

    # 3. Make transactions.category nullable (was NOT NULL with default
    #    "Uncategorized"). Existing "Uncategorized" rows are left as-is.
    op.alter_column(
        "transactions",
        "category",
        existing_type=sa.String(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "category",
        existing_type=sa.String(),
        nullable=False,
        server_default="Uncategorized",
    )
    op.drop_column("transactions", "provider_category")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
