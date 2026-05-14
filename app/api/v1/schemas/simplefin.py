from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class SimplefinConnectRequest(BaseModel):
    setup_token: str


class SimplefinStatusResponse(BaseModel):
    connected: bool
    institutions: Optional[List[str]] = None
    last_synced_at: Optional[datetime] = None


class NewTransaction(BaseModel):
    id: str
    title: str
    amount: Decimal
    account_name: Optional[str] = None

    model_config = {"json_encoders": {Decimal: float}}


class SimplefinFetchResponse(BaseModel):
    ok: bool
    accounts_updated: int
    transactions_added: int
    new_transactions: List[NewTransaction] = []
