import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELED = "canceled"


class RecurrenceUnit(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Subscription(Base):
    """Recurring charge/income template used for grouping transactions.

    Phase 1 keeps matching metadata simple (merchant/category/amount range +
    recurrence interval/unit) so we can add auto-detection logic later.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("recurrence_interval > 0", name="ck_subscriptions_recurrence_interval_positive"),
        CheckConstraint(
            "end_date IS NULL OR status <> 'active'",
            name="ck_subscriptions_end_date_not_active",
        ),
        CheckConstraint(
            "min_amount IS NULL OR max_amount IS NULL OR min_amount <= max_amount",
            name="ck_subscriptions_amount_range_valid",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    household_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("households.id"), nullable=False, index=True, default=1
    )
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    recurrence_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recurrence_unit: Mapped[str] = mapped_column(String, nullable=False, default=RecurrenceUnit.MONTH)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=SubscriptionStatus.ACTIVE, index=True)
    auto_link_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    matching_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    transactions = relationship(
        "Transaction",
        back_populates="subscription",
        passive_deletes=True,
    )
