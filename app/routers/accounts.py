from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import date

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account as AccountModel
from app.models.user import User
from app.schemas.account import Account
from app.schemas.account_snapshot import NetWorthHistoryEntry
from app.services.net_worth import get_net_worth_history, create_snapshot

router = APIRouter()

_SEED: List[Account] = [
    Account(id="a1", name="Main Checking",        type="checking",    balance=Decimal("4823.67"),  available_balance=Decimal("4823.67"),  institution_name="Chase Bank", color="#2196F3"),
    Account(id="a2", name="Emergency Fund",       type="savings",     balance=Decimal("12500.00"), available_balance=Decimal("12500.00"), institution_name="Ally Bank",  color="#4CAF50"),
    Account(id="a3", name="Visa Platinum",        type="credit_card", balance=Decimal("-1247.50"), available_balance=None,                institution_name="Chase Bank", color="#FF9800"),
    Account(id="a4", name="Investment Portfolio", type="investment",  balance=Decimal("28350.00"), available_balance=None,                institution_name="Fidelity",   color="#9C27B0"),
    Account(id="a5", name="Cash Wallet",          type="cash",        balance=Decimal("245.00"),   available_balance=None,                institution_name=None,         color="#009688"),
]


@router.get("/accounts", response_model=List[Account])
async def get_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountModel).order_by(AccountModel.name))
    rows = result.scalars().all()
    return [
        Account(
            id=r.id, name=r.name, type=r.type, balance=r.balance,
            available_balance=r.available_balance,
            institution_name=r.institution_name, color=r.color,
            created_at=r.created_at, updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/accounts/net-worth-history", response_model=List[NetWorthHistoryEntry])
async def get_net_worth_history_endpoint(
    period: str = Query("1month", description="Time period: 1week, 1month, 3months, 6months, 1year"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get net worth history for the current household over a specified period.

    Supports time periods: 1week, 1month, 3months, 6months, 1year
    Returns list of daily snapshots with date and net_worth values.
    """
    history = await get_net_worth_history(db, current_user.household_id, period)
    return history


@router.post("/accounts/snapshots/create")
async def create_daily_snapshot(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a daily snapshot of net worth for the current household.

    This endpoint can be called by a scheduled task (cron, Lambda, Cloud Scheduler, etc.)
    or manually triggered. It calculates current net worth and stores a snapshot.

    Returns the created or updated snapshot.
    """
    today = date.today()
    snapshot = await create_snapshot(db, current_user.household_id, today)

    await db.commit()

    return {
        "id": snapshot.id,
        "household_id": snapshot.household_id,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "net_worth": float(snapshot.net_worth),
        "total_assets": float(snapshot.total_assets),
        "total_liabilities": float(snapshot.total_liabilities),
    }
