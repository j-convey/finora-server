from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SimplefinConnectRequest(BaseModel):
    setup_token: str


class SimplefinStatusResponse(BaseModel):
    connected: bool
    institutions: Optional[List[str]] = None
    last_synced_at: Optional[datetime] = None


class SimplefinFetchResponse(BaseModel):
    ok: bool
    accounts_updated: int
    transactions_added: int
