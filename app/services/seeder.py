"""
Seed service — inserts default data on first startup.

Uses INSERT ... ON CONFLICT DO NOTHING so re-runs are safe.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.budget import Budget as BudgetModel
from app.models.category import Category as CategoryModel
from app.models.account_snapshot import AccountSnapshot as AccountSnapshotModel

_DEFAULT_CATEGORIES = [
    # Income
    "Paychecks",
    "Interest",
    "Business Income",
    "Other Income",
    # Gifts & Donations
    "Charity",
    "Gifts",
    # Auto & Transport
    "Auto Payment",
    "Public Transit",
    "Gas",
    "Auto Maintenance",
    "Parking & Tolls",
    "Taxi & Ride Shares",
    # Housing
    "Mortgage",
    "Rent",
    "Home Improvement",
    # Bills & Utilities
    "Garbage",
    "Water",
    "Gas & Electric",
    "Internet & Cable",
    "Phone",
    # Food & Dining
    "Groceries",
    "Restaurants & Bars",
    "Coffee Shops",
    # Travel & Lifestyle
    "Travel & Vacation",
    "Entertainment & Recreation",
    "Personal",
    "Pets",
    "Fun Money",
    # Shopping
    "Shopping",
    "Clothing",
    "Furniture & Housewares",
    "Electronics",
    # Children
    "Child Care",
    "Child Activities",
    # Education
    "Student Loans",
    "Education",
    # Health & Wellness
    "Medical",
    "Dentist",
    "Fitness",
    # Financial
    "Loan Repayment",
    "Financial & Legal Services",
    "Financial Fees",
    "Cash & ATM",
    "Insurance",
    "Taxes",
    # Other
    "Uncategorized",
    "Check",
    "Miscellaneous",
    # Business
    "Advertising & Promotion",
    "Business Utilities & Communication",
    "Employee Wages & Contract Labor",
    "Business Travel & Meals",
    "Business Auto Expenses",
    "Business Insurance",
    "Office Supplies & Expenses",
    "Office Rent",
    "Postage & Shipping",
    # Transfers
    "Transfer",
    "Credit Card Payment",
    "Balance Adjustments",
]

_DEFAULT_BUDGETS = [
    {"id": "b1", "category": "Groceries",     "allocated": Decimal("400.00"), "color": "#66BB6A"},
    {"id": "b2", "category": "Dining",        "allocated": Decimal("200.00"), "color": "#FFA726"},
    {"id": "b3", "category": "Transport",     "allocated": Decimal("150.00"), "color": "#42A5F5"},
    {"id": "b4", "category": "Entertainment", "allocated": Decimal("100.00"), "color": "#AB47BC"},
    {"id": "b5", "category": "Subscriptions", "allocated": Decimal("50.00"),  "color": "#26A69A"},
    {"id": "b6", "category": "Health",        "allocated": Decimal("100.00"), "color": "#EF5350"},
    {"id": "b7", "category": "Shopping",      "allocated": Decimal("150.00"), "color": "#EC407A"},
]


async def seed_categories() -> None:
    """Insert default system categories if any are missing.

    Safe to re-run: only names not yet present are inserted, so adding a new
    default in code will be picked up on the next startup without disturbing
    existing rows.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CategoryModel.name))
        existing = {name for (name,) in result.all()}

        added = 0
        for index, name in enumerate(_DEFAULT_CATEGORIES):
            if name in existing:
                continue
            db.add(
                CategoryModel(
                    name=name,
                    is_system=True,
                    sort_order=index,
                )
            )
            added += 1

        if added:
            await db.commit()
            print(f"✅ Seeded {added} default categories.")


async def seed_budgets() -> None:
    """Insert default budget rows if the table is empty."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BudgetModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        for row in _DEFAULT_BUDGETS:
            db.add(BudgetModel(**row))

        await db.commit()
        print(f"✅ Seeded {len(_DEFAULT_BUDGETS)} default budgets.")


async def seed_account_snapshots() -> None:
    """Insert initial account snapshots for demonstration and testing."""
    async with AsyncSessionLocal() as db:
        # Check if snapshots already exist
        result = await db.execute(select(AccountSnapshotModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        # Create snapshots for the last 30 days
        household_id = 1
        today = date.today()
        base_net_worth = Decimal("45671.17")
        base_assets = Decimal("46918.67")
        base_liabilities = Decimal("1247.50")
        
        # Add some variation to make the chart interesting
        for i in range(30, -1, -1):
            snapshot_date = today - timedelta(days=i)
            
            # Simulate gradual growth with some daily fluctuations
            progress = Decimal(str((30 - i) / 30))
            variance = Decimal(str(-5000 + (i % 7) * 1000))  # Fluctuation based on day
            
            net_worth = base_net_worth + (Decimal("20000") * progress) + variance
            total_assets = base_assets + (Decimal("20500") * progress) + variance
            total_liabilities = base_liabilities - (Decimal("500") * progress)
            
            snapshot = AccountSnapshotModel(
                household_id=household_id,
                snapshot_date=snapshot_date,
                net_worth=net_worth,
                total_assets=total_assets,
                total_liabilities=max(Decimal("0"), total_liabilities),  # Ensure non-negative
            )
            db.add(snapshot)

        await db.commit()
        print(f"✅ Seeded 31 account snapshots for household {household_id}.")
