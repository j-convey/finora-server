from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Integer, Date, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (
        UniqueConstraint("household_id", "snapshot_date", name="uq_household_snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    household_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_liabilities: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
