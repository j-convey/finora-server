from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class Transaction(BaseModel):
    id: str
    title: str
    original_description: Optional[str] = None
    merchant_name: Optional[str] = None
    provider_transaction_id: Optional[str] = None
    amount: Decimal
    type: str  # income | expense | transfer
    category: Optional[str] = None
    provider_category: Optional[str] = None
    date: datetime
    pending: bool = False
    account_id: Optional[str] = None
    subscription_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"json_encoders": {Decimal: float}}


class TransactionUpdate(BaseModel):
    """Partial update payload for PATCH /transactions/:id.

    Only fields the client is allowed to mutate are accepted. All fields are
    optional so the caller may send any subset.
    """

    title: Optional[str] = None
    category: Optional[str] = None
    subscription_id: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}
