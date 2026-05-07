from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, func, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    # Canonical category name from the `categories` table. NULL = uncategorized.
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    # Raw category string from the data provider (e.g. SimpleFIN). Preserved
    # for debugging / future auto-mapping; never shown to the user directly.
    provider_category: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subscription_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    subscription = relationship("Subscription", back_populates="transactions")
