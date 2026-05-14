from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class NetWorthHistoryEntry(BaseModel):
    """Single net worth entry for the history chart."""
    date: str  # ISO format string: "2026-11-07"
    net_worth: float


class NetWorthHistory(BaseModel):
    """Collection of net worth history entries."""
    entries: list[NetWorthHistoryEntry]

    model_config = {"json_encoders": {Decimal: float}}


class AccountSnapshotBase(BaseModel):
    """Base account snapshot schema."""
    household_id: int
    snapshot_date: date
    net_worth: Decimal
    total_assets: Decimal
    total_liabilities: Decimal


class AccountSnapshot(AccountSnapshotBase):
    """Full account snapshot schema."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"json_encoders": {Decimal: float}}
