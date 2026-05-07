"""Add transaction data validation constraints

Revision ID: 002_add_transaction_constraints
Revises: 001_add_transaction_indexes
Create Date: 2026-05-06 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_transaction_constraints'
down_revision = '001_add_transaction_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add check constraints to ensure data quality."""
    # Ensure amount is always positive
    op.create_check_constraint(
        'ck_transaction_amount_positive',
        'transactions',
        'amount > 0',
    )
    
    # Ensure type is one of the valid values
    op.create_check_constraint(
        'ck_transaction_type_valid',
        'transactions',
        "type IN ('income', 'expense', 'transfer')",
    )


def downgrade() -> None:
    """Drop data validation constraints."""
    op.drop_constraint('ck_transaction_type_valid', 'transactions')
    op.drop_constraint('ck_transaction_amount_positive', 'transactions')
