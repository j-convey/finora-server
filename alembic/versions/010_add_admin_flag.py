"""Add is_admin flag to users table for role-based access control.

Revision ID: 010_add_admin_flag
Revises: 009_add_reimbursements
Create Date: 2026-05-11 00:00:00.000000

Changes:
  - users.is_admin (Boolean, default=False, NOT NULL)
      Identifies admin users who can access protected endpoints like
      reset-database, export-database, and import-database.
      All existing users default to non-admin.
"""
from alembic import op
import sqlalchemy as sa


revision = "010_add_admin_flag"
down_revision = "009_add_reimbursements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_admin column with default=False for existing users
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
