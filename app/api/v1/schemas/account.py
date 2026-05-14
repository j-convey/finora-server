from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class Account(BaseModel):
    id: str
    name: str
    type: str  # checking | savings | credit_card | investment | cash
    balance: Decimal
    available_balance: Optional[Decimal] = None
    institution_name: Optional[str] = None
    color: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"json_encoders": {Decimal: float}}
