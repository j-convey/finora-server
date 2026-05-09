from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransactionReimbursement(Base):
    """Junction table linking an expense transaction to an income transaction.

    Supports partial reimbursements: amount may be less than either transaction's
    full amount. Multiple rows can exist for the same expense (multiple partial
    reimbursements) but each (expense_id, income_id) pair must be unique.

    ON DELETE CASCADE on both FK columns ensures orphan cleanup when either
    transaction is deleted.
    """

    __tablename__ = "transaction_reimbursements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_reimb_amount_positive"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)

    expense_transaction_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    income_transaction_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stored as Numeric(19,4) to match transactions.amount exactly.
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # users.id is Integer in this schema
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    expense_transaction = relationship(
        "Transaction",
        foreign_keys=[expense_transaction_id],
        back_populates="reimbursed_by",
    )
    income_transaction = relationship(
        "Transaction",
        foreign_keys=[income_transaction_id],
        back_populates="reimburses",
    )
    created_by = relationship("User", foreign_keys=[created_by_user_id])
