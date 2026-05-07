"""Add households table, extend users for auth, add refresh_tokens

Revision ID: 005_add_auth
Revises: 004_add_subscriptions_table
Create Date: 2026-05-07 00:00:00.000000

Changes:
  - Creates 'households' table (one per family/couple)
  - Adds household_id + profile_picture_path to users
  - Migrates subscriptions.user_id  → household_id
  - Migrates account_snapshots.user_id → household_id
  - Creates refresh_tokens table (opaque token hashes for session management)

TODO (OIDC — Pocket ID):
  When implementing OIDC, add a follow-up migration that:
  - Adds users.oidc_subject  (the "sub" claim from the provider)
  - Adds users.oidc_provider (provider identifier, e.g. "pocket_id")
  - Creates an oidc_config table (issuer_url, authorization_endpoint,
    token_endpoint, userinfo_endpoint, jwks_uri, client_id,
    client_secret_encrypted, signing_algorithm, auto_launch bool, enabled bool)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005_add_auth"
down_revision = "004_add_subscriptions_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. households ────────────────────────────────────────────────────────
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Seed a default household so all existing rows (user_id=1) resolve correctly.
    op.execute("INSERT INTO households (id, name) VALUES (1, 'My Household')")
    # Advance the sequence past 1 so the next INSERT gets id=2, not a collision.
    op.execute("SELECT setval('households_id_seq', 1)")

    # ── 2. Extend users ──────────────────────────────────────────────────────
    op.add_column("users", sa.Column("household_id", sa.Integer(), nullable=True))
    op.execute("UPDATE users SET household_id = 1")
    op.alter_column("users", "household_id", nullable=False)
    op.create_foreign_key(
        "fk_users_household_id", "users", "households", ["household_id"], ["id"]
    )
    op.create_index("ix_users_household_id", "users", ["household_id"])

    op.add_column("users", sa.Column("profile_picture_path", sa.String(), nullable=True))

    # Make hashed_password nullable so a future OIDC-only user can be created
    # without a local password.
    op.alter_column("users", "hashed_password", nullable=True)

    # TODO (OIDC): Uncomment when implementing Pocket ID SSO:
    # op.add_column("users", sa.Column("oidc_subject", sa.String(), nullable=True))
    # op.add_column("users", sa.Column("oidc_provider", sa.String(), nullable=True))
    # op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"])

    # ── 3. subscriptions: user_id → household_id ─────────────────────────────
    op.add_column("subscriptions", sa.Column("household_id", sa.Integer(), nullable=True))
    op.execute("UPDATE subscriptions SET household_id = user_id")
    op.alter_column("subscriptions", "household_id", nullable=False, server_default="1")
    op.create_foreign_key(
        "fk_subscriptions_household_id", "subscriptions", "households",
        ["household_id"], ["id"],
    )
    op.create_index("ix_subscriptions_household_id", "subscriptions", ["household_id"])
    op.drop_column("subscriptions", "user_id")

    # ── 4. account_snapshots: user_id → household_id ─────────────────────────
    op.drop_constraint("uq_user_snapshot_date", "account_snapshots", type_="unique")
    op.add_column("account_snapshots", sa.Column("household_id", sa.Integer(), nullable=True))
    op.execute("UPDATE account_snapshots SET household_id = user_id")
    op.alter_column("account_snapshots", "household_id", nullable=False, server_default="1")
    op.create_foreign_key(
        "fk_account_snapshots_household_id", "account_snapshots", "households",
        ["household_id"], ["id"],
    )
    op.create_index("ix_account_snapshots_household_id", "account_snapshots", ["household_id"])
    op.create_unique_constraint(
        "uq_household_snapshot_date", "account_snapshots", ["household_id", "snapshot_date"]
    )
    op.drop_column("account_snapshots", "user_id")

    # ── 5. refresh_tokens ────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # TODO (OIDC): Create oidc_config table in a future migration.
    # It should be a singleton row (like simplefin_config) with columns:
    #   enabled, issuer_url, authorization_endpoint, token_endpoint,
    #   userinfo_endpoint, jwks_uri, client_id, client_secret_encrypted,
    #   signing_algorithm (default "RS256"), auto_launch (bool)


def downgrade() -> None:
    op.drop_table("refresh_tokens")

    # Restore account_snapshots
    op.drop_constraint("uq_household_snapshot_date", "account_snapshots", type_="unique")
    op.drop_index("ix_account_snapshots_household_id", table_name="account_snapshots")
    op.drop_constraint("fk_account_snapshots_household_id", "account_snapshots", type_="foreignkey")
    op.add_column("account_snapshots", sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE account_snapshots SET user_id = household_id")
    op.alter_column("account_snapshots", "user_id", nullable=False)
    op.create_unique_constraint("uq_user_snapshot_date", "account_snapshots", ["user_id", "snapshot_date"])
    op.drop_column("account_snapshots", "household_id")

    # Restore subscriptions
    op.drop_index("ix_subscriptions_household_id", table_name="subscriptions")
    op.drop_constraint("fk_subscriptions_household_id", "subscriptions", type_="foreignkey")
    op.add_column("subscriptions", sa.Column("user_id", sa.Integer(), nullable=True, server_default="1"))
    op.execute("UPDATE subscriptions SET user_id = household_id")
    op.alter_column("subscriptions", "user_id", nullable=False)
    op.drop_column("subscriptions", "household_id")

    # Restore users
    op.drop_index("ix_users_household_id", table_name="users")
    op.drop_constraint("fk_users_household_id", "users", type_="foreignkey")
    op.drop_column("users", "profile_picture_path")
    op.drop_column("users", "household_id")
    op.alter_column("users", "hashed_password", nullable=False)

    op.drop_table("households")
