"""
Net worth calculation and snapshot service.

Handles calculating net worth from accounts, creating daily snapshots, 
and retrieving historical net worth data.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.account_snapshot_repository import AccountSnapshotRepository
from app.infrastructure.models.account_snapshot import AccountSnapshot as AccountSnapshotModel
from app.api.v1.schemas.account_snapshot import NetWorthHistoryEntry


async def calculate_net_worth(db: AsyncSession, household_id: int) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate total net worth for a household from all their accounts.
    
    Returns:
        tuple: (net_worth, total_assets, total_liabilities)
    """
    accounts = await AccountRepository(db).list_all()
    
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    
    for account in accounts:
        balance = account.balance
        
        # Determine if asset or liability
        if account.type == "credit_card":
            # Credit cards are liabilities (balance is negative for money owed)
            if balance < 0:
                total_liabilities += abs(balance)
            else:
                total_assets += balance
        else:
            # All other types are assets (checking, savings, investment, cash)
            if balance > 0:
                total_assets += balance
            elif balance < 0:
                total_liabilities += abs(balance)
    
    net_worth = total_assets - total_liabilities
    
    return net_worth, total_assets, total_liabilities


async def create_snapshot(
    db: AsyncSession,
    household_id: int,
    snapshot_date: date,
) -> AccountSnapshotModel:
    """
    Create or update a daily snapshot for a household.
    
    If a snapshot already exists for the household on that date, it will be updated.
    """
    net_worth, total_assets, total_liabilities = await calculate_net_worth(db, household_id)

    snapshot_repo = AccountSnapshotRepository(db)
    existing_snapshot = await snapshot_repo.get_by_household_and_date(household_id, snapshot_date)
    
    if existing_snapshot:
        existing_snapshot.net_worth = net_worth
        existing_snapshot.total_assets = total_assets
        existing_snapshot.total_liabilities = total_liabilities
        await db.flush()
        return existing_snapshot
    else:
        snapshot = AccountSnapshotModel(
            household_id=household_id,
            snapshot_date=snapshot_date,
            net_worth=net_worth,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot


async def get_net_worth_history(
    db: AsyncSession,
    household_id: int,
    period: str = "1month",
) -> list[NetWorthHistoryEntry]:
    """
    Retrieve net worth history for a household over a specified period.
    
    Args:
        db: Database session
        household_id: Household ID
        period: Time period - "1week", "1month", "3months", "6months", "1year"
    
    Returns:
        List of NetWorthHistoryEntry objects sorted by date
    """
    today = date.today()
    period_days = {
        "1week": 7,
        "1month": 30,
        "3months": 90,
        "6months": 180,
        "1year": 365,
    }
    
    days_back = period_days.get(period, 30)
    start_date = today - timedelta(days=days_back)

    snapshots = await AccountSnapshotRepository(db).get_history(household_id, start_date, today)
    
    return [
        NetWorthHistoryEntry(
            date=snapshot.snapshot_date.isoformat(),
            net_worth=float(snapshot.net_worth),
        )
        for snapshot in snapshots
    ]
