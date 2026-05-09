from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ReimbursementCreate(BaseModel):
    """Payload for POST /api/v1/transactions/reimbursements."""

    expense_transaction_id: str
    income_transaction_id: str
    # Stored as Numeric(19,4) — same unit as transactions.amount (e.g. 65.00 = $65.00)
    amount: Decimal
    notes: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class ReimbursementUpdate(BaseModel):
    """Payload for PUT /api/v1/transactions/reimbursements/{id}.

    Only amount and notes are mutable after creation.
    """

    amount: Optional[Decimal] = None
    notes: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("amount must be greater than zero")
        return v

    model_config = ConfigDict(extra="ignore")


class ReimbursementResponse(BaseModel):
    """API response shape for a single TransactionReimbursement row."""

    id: str
    expense_transaction_id: str
    income_transaction_id: str
    amount: Decimal
    notes: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReimbursementListResponse(BaseModel):
    """Envelope returned by GET /api/v1/transactions/{id}/reimbursements.

    Includes per-transaction allocation totals so clients can render
    remaining capacity without a second round-trip.
    """

    transaction_id: str
    # The full absolute amount of the transaction (always positive)
    transaction_amount: Decimal
    # Sum of all linked reimbursement amounts
    allocated_amount: Decimal
    # transaction_amount - allocated_amount (>= 0)
    remaining_amount: Decimal
    reimbursements: list[ReimbursementResponse]

    model_config = ConfigDict(from_attributes=True)
