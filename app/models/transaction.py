from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, Integer, func, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref

from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        CheckConstraint("type IN ('income', 'expense', 'transfer')", name="ck_transaction_type_valid"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Display name — cleaned up or user-edited
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Raw string from the bank provider (never overwritten after initial import)
    original_description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Merchant name parsed from the raw description (SimpleFIN / AI-derived)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Provider's own transaction ID — used for deduplication across syncs
    provider_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # income | expense | transfer
    # FK to canonical category — user-facing classification. NULL = uncategorized.
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Raw category string from the data provider (e.g. SimpleFIN). Immutable after import.
    provider_category: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # FK to account — every transaction must belong to an account.
    account_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    # Split transaction support — see docs/architecture for double-counting rules.
    # True only on the "ghost" parent created when a user splits a transaction.
    # Budget / analytics queries MUST filter WHERE is_split_parent = FALSE.
    is_split_parent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    # Points to the parent row for child splits. NULL on all normal + parent rows.
    # Bank-reconciliation queries MUST filter WHERE parent_transaction_id IS NULL.
    parent_transaction_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Set by SimpleFIN sync when a split parent's amount drifts (pending→posted).
    # Prompts the client to let the user re-reconcile.
    requires_user_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    category_rel = relationship("Category", foreign_keys=[category_id], lazy="select")
    subscription = relationship("Subscription", back_populates="transactions")
    # Children of this transaction (populated when is_split_parent=True).
    # The backref "parent" gives each child a .parent accessor pointing to this row.
    children = relationship(
        "Transaction",
        backref=backref("parent", remote_side="Transaction.id"),
        cascade="all, delete-orphan",
        foreign_keys="Transaction.parent_transaction_id",
    )
