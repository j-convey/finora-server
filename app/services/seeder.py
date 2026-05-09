"""
Seed service — inserts default data on first startup.

Uses INSERT ... ON CONFLICT DO NOTHING so re-runs are safe.
"""
import csv
import os
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.budget import Budget as BudgetModel
from app.models.category import Category as CategoryModel
from app.models.account_snapshot import AccountSnapshot as AccountSnapshotModel
from app.models.account import Account as AccountModel
from app.models.transaction import Transaction as TransactionModel
from app.models.subscription import Subscription as SubscriptionModel

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

# Budget definitions use category names; IDs are looked up at seed time.
_DEFAULT_BUDGETS = [
    {"id": "b1", "household_id": 1, "category_name": "Groceries",              "allocated": Decimal("400.00"), "color": "#66BB6A"},
    {"id": "b2", "household_id": 1, "category_name": "Restaurants & Bars",     "allocated": Decimal("200.00"), "color": "#FFA726"},
    {"id": "b3", "household_id": 1, "category_name": "Gas",                    "allocated": Decimal("150.00"), "color": "#42A5F5"},
    {"id": "b4", "household_id": 1, "category_name": "Entertainment & Recreation", "allocated": Decimal("100.00"), "color": "#AB47BC"},
    {"id": "b5", "household_id": 1, "category_name": "Shopping",               "allocated": Decimal("150.00"), "color": "#EC407A"},
    {"id": "b6", "household_id": 1, "category_name": "Medical",                "allocated": Decimal("100.00"), "color": "#EF5350"},
    {"id": "b7", "household_id": 1, "category_name": "Fitness",                "allocated": Decimal("50.00"),  "color": "#26A69A"},
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


async def _load_category_name_to_id(db) -> dict[str, int]:
    """Return a lowercase name → id mapping for all system categories."""
    result = await db.execute(
        select(CategoryModel.id, CategoryModel.name).where(
            CategoryModel.household_id.is_(None)
        )
    )
    return {name.lower(): cat_id for cat_id, name in result.all()}


async def seed_budgets() -> None:
    """Insert default budget rows if the table is empty."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BudgetModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        cat_map = await _load_category_name_to_id(db)

        for row in _DEFAULT_BUDGETS:
            category_id = cat_map.get(row["category_name"].lower())
            if category_id is None:
                print(f"⚠️  Budget skipped — unknown category: {row['category_name']!r}")
                continue
            db.add(BudgetModel(
                id=row["id"],
                household_id=row["household_id"],
                category_id=category_id,
                allocated=row["allocated"],
                color=row["color"],
            ))

        await db.commit()
        print(f"✅ Seeded {len(_DEFAULT_BUDGETS)} default budgets.")


async def seed_accounts() -> None:
    """Create demo accounts: checking, savings, and credit card."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AccountModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        accounts = [
            {
                "id": "acct_checking_001",
                "household_id": 1,
                "name": "Chase Checking",
                "type": "checking",
                "balance": Decimal("4850.32"),
                "available_balance": Decimal("4850.32"),
                "institution_name": "Chase Bank",
                "color": "#42A5F5",
            },
            {
                "id": "acct_savings_001",
                "household_id": 1,
                "name": "Capital One Savings",
                "type": "savings",
                "balance": Decimal("15250.00"),
                "available_balance": Decimal("15250.00"),
                "institution_name": "Capital One",
                "color": "#66BB6A",
            },
            {
                "id": "acct_credit_001",
                "household_id": 1,
                "name": "Amazon Prime Rewards Visa",
                "type": "credit",
                "balance": Decimal("-2347.89"),  # Negative = money owed
                "available_balance": Decimal("2652.11"),  # Available credit
                "institution_name": "Chase Bank",
                "color": "#FFA726",
            },
        ]

        for acc in accounts:
            db.add(AccountModel(**acc))

        await db.commit()
        print(f"✅ Seeded {len(accounts)} demo accounts.")


async def seed_subscriptions() -> None:
    """Create realistic recurring subscriptions."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SubscriptionModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        today = date.today()
        subscriptions = [
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Netflix",
                "merchant_name": "Netflix",
                "category": "Entertainment & Recreation",
                "expected_amount": Decimal("15.99"),
                "min_amount": Decimal("15.99"),
                "max_amount": Decimal("20.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=120),
                "next_due_date": today + timedelta(days=5),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Spotify Premium",
                "merchant_name": "Spotify",
                "category": "Entertainment & Recreation",
                "expected_amount": Decimal("11.99"),
                "min_amount": Decimal("11.99"),
                "max_amount": Decimal("14.99"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=150),
                "next_due_date": today + timedelta(days=8),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Planet Fitness",
                "merchant_name": "Planet Fitness",
                "category": "Fitness",
                "expected_amount": Decimal("23.00"),
                "min_amount": Decimal("22.00"),
                "max_amount": Decimal("25.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=200),
                "next_due_date": today + timedelta(days=12),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "AWS",
                "merchant_name": "Amazon Web Services",
                "category": "Business Utilities & Communication",
                "expected_amount": Decimal("45.50"),
                "min_amount": Decimal("40.00"),
                "max_amount": Decimal("80.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=180),
                "next_due_date": today + timedelta(days=2),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "GitHub Pro",
                "merchant_name": "GitHub",
                "category": "Business Utilities & Communication",
                "expected_amount": Decimal("4.00"),
                "min_amount": Decimal("4.00"),
                "max_amount": Decimal("4.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=90),
                "next_due_date": today + timedelta(days=15),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Adobe Creative Cloud",
                "merchant_name": "Adobe",
                "category": "Software & Services",
                "expected_amount": Decimal("59.99"),
                "min_amount": Decimal("59.99"),
                "max_amount": Decimal("65.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=130),
                "next_due_date": today + timedelta(days=10),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Internet & Cable",
                "merchant_name": "Comcast",
                "category": "Internet & Cable",
                "expected_amount": Decimal("89.99"),
                "min_amount": Decimal("85.00"),
                "max_amount": Decimal("95.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=240),
                "next_due_date": today + timedelta(days=3),
                "status": "active",
                "auto_link_enabled": True,
            },
            {
                "id": str(uuid.uuid4()),
                "household_id": 1,
                "name": "Apple One",
                "merchant_name": "Apple",
                "category": "Entertainment & Recreation",
                "expected_amount": Decimal("34.95"),
                "min_amount": Decimal("34.95"),
                "max_amount": Decimal("40.00"),
                "recurrence_interval": 1,
                "recurrence_unit": "month",
                "start_date": today - timedelta(days=60),
                "next_due_date": today + timedelta(days=18),
                "status": "active",
                "auto_link_enabled": True,
            },
        ]

        for sub in subscriptions:
            db.add(SubscriptionModel(**sub))

        await db.commit()
        print(f"✅ Seeded {len(subscriptions)} demo subscriptions.")


async def seed_transactions() -> None:
    """Load transactions from CSV file.
    
    CSV should be at app/data/transactions.csv with columns:
    days_ago, title, merchant_name, original_description, amount, type, category, account_id, subscription_name
    
    The 'category' column contains a category name (string). The seeder looks up
    the corresponding category_id from the categories table. Unknown names fall
    back to 'Uncategorized'.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TransactionModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        # Load category name → id mapping (system categories only)
        cat_map = await _load_category_name_to_id(db)
        uncategorized_id = cat_map.get("uncategorized")

        # Load subscription name → id mapping
        subs = await db.execute(select(SubscriptionModel).where(
            SubscriptionModel.household_id == 1
        ))
        subscription_map = {sub.name.lower(): sub.id for sub in subs.scalars().all()}

        csv_path = os.path.join(os.path.dirname(__file__), "../data/transactions.csv")

        if not os.path.exists(csv_path):
            print(f"⚠️  Transaction CSV not found at {csv_path}")
            return

        today = date.today()
        transactions = []
        transaction_id_counter = 1000

        try:
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    days_ago = int(row["days_ago"])
                    transaction_date = today + timedelta(days=days_ago)

                    # Resolve category name → id
                    category_name = row.get("category", "").strip()
                    category_id = cat_map.get(category_name.lower(), uncategorized_id)

                    # Match subscription name (case-insensitive)
                    subscription_name = row.get("subscription_name", "").strip()
                    subscription_id = None
                    if subscription_name:
                        subscription_id = subscription_map.get(subscription_name.lower())

                    transactions.append(
                        TransactionModel(
                            id=f"txn_{transaction_id_counter}",
                            title=row["title"].strip(),
                            original_description=row["original_description"].strip(),
                            merchant_name=row["merchant_name"].strip(),
                            provider_transaction_id=f"provider_{transaction_id_counter}",
                            amount=Decimal(row["amount"].strip()),
                            type=row["type"].strip(),
                            category_id=category_id,
                            provider_category=category_name,  # preserve raw name as provider string
                            date=datetime.combine(transaction_date, datetime.min.time()),
                            pending=False,
                            account_id=row["account_id"].strip(),
                            subscription_id=subscription_id,
                        )
                    )
                    transaction_id_counter += 1

            for txn in transactions:
                db.add(txn)

            await db.commit()
            print(f"✅ Seeded {len(transactions)} transactions from CSV.")
        except Exception as exc:
            print(f"❌ Failed to load transactions from CSV: {exc}")
            raise






async def seed_account_snapshots() -> None:
    """Insert account snapshots for 6 months of net worth history."""
    async with AsyncSessionLocal() as db:
        # Check if snapshots already exist
        result = await db.execute(select(AccountSnapshotModel).limit(1))
        if result.scalars().first() is not None:
            return  # already seeded

        # Create snapshots for the last 180 days
        household_id = 1
        today = date.today()
        
        # Realistic starting position: checking + savings - credit card debt
        base_checking = Decimal("3000.00")
        base_savings = Decimal("10000.00")
        base_cc_debt = Decimal("500.00")
        base_net_worth = base_checking + base_savings - base_cc_debt
        
        # Add some variation to make the chart interesting
        for i in range(180, -1, -1):
            snapshot_date = today - timedelta(days=i)
            
            # Simulate gradual wealth accumulation with spending patterns
            progress = Decimal(str((180 - i) / 180))
            # Paychecks add ~$2500 biweekly, expenses subtract gradually
            paycheck_count = (180 - i) // 14  # Every 14 days
            expense_trend = Decimal(str(((180 - i) % 14) / 14)) * Decimal("100")  # Spending pattern
            
            # Daily variance
            variance = Decimal(str(-2000 + (i % 7) * 500))
            
            total_assets = (
                base_checking 
                + base_savings 
                + (Decimal("2500") * Decimal(str(paycheck_count)))  # Accumulated paychecks
                - (Decimal("150") * Decimal(str((180 - i) / 180)))  # Daily expenses
                + variance
            )
            
            # Credit card oscillates based on spending
            cc_debt = base_cc_debt + (Decimal("500") * Decimal(str((i % 14) / 14)))
            total_liabilities = max(Decimal("0"), cc_debt)
            
            net_worth = total_assets - total_liabilities
            
            snapshot = AccountSnapshotModel(
                household_id=household_id,
                snapshot_date=snapshot_date,
                net_worth=net_worth,
                total_assets=max(Decimal("0"), total_assets),
                total_liabilities=total_liabilities,
            )
            db.add(snapshot)

        await db.commit()
        print(f"✅ Seeded 181 account snapshots for 6-month net worth history.")
