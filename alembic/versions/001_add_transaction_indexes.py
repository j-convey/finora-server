"""Add transaction performance indexes for reports aggregation

Revision ID: 001_add_transaction_indexes
Revises: 
Create Date: 2026-05-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_transaction_indexes'
down_revision = '000_create_initial_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add indexes to transactions table for reports page performance."""
    op.create_index('idx_transactions_date', 'transactions', [sa.text('date DESC')])
    op.create_index('idx_transactions_category', 'transactions', ['category'])
    op.create_index('idx_transactions_type', 'transactions', ['type'])
    op.create_index('idx_transactions_type_date', 'transactions', ['type', sa.text('date DESC')])
    op.create_index('idx_transactions_pending', 'transactions', ['pending'])


def downgrade() -> None:
    """Drop all transaction indexes."""
    op.drop_index('idx_transactions_pending', table_name='transactions')
    op.drop_index('idx_transactions_type_date', table_name='transactions')
    op.drop_index('idx_transactions_type', table_name='transactions')
    op.drop_index('idx_transactions_category', table_name='transactions')
    op.drop_index('idx_transactions_date', table_name='transactions')
