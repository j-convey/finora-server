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
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.infrastructure.models.budget import Budget as BudgetModel
from app.infrastructure.models.category import Category as CategoryModel
from app.infrastructure.models.account_snapshot import AccountSnapshot as AccountSnapshotModel
from app.infrastructure.models.account import Account as AccountModel
from app.infrastructure.models.transaction import Transaction as TransactionModel
from app.infrastructure.models.subscription import Subscription as SubscriptionModel

logger = get_logger(__name__)

# Grouped category structure.  Each key is the display group name; the value
# carries the type that all subcategories inherit plus the ordered subcategory
# list.  sort_order is assigned globally (sequential across all groups) so the
# DB can order a flat list correctly.
_DEFAULT_CATEGORY_GROUPS: dict[str, dict] = {
    "Income": {
        "type": "income",
        "subcategories": [
            "Paychecks",
            "Bonuses & Commissions",
            "Overtime",
            "Business Income / Revenue",
            "Freelance / Side Hustle Income",
            "Self-Employment Income",
            "Interest Income",
            "Dividends & Investment Income",
            "Rental Income",
            "Pension / Retirement Income",
            "Government Benefits (Social Security, etc.)",
            "Tax Refunds & Credits",
            "Reimbursements",
            "Gifts Received",
            "Alimony / Child Support Received",
            "Other Income",
        ],
    },
    "Housing": {
        "type": "expense",
        "subcategories": [
            "Mortgage",
            "Rent",
            "Property Taxes",
            "HOA / Condo Fees",
            "Homeowners / Renters Insurance",
            "Home Maintenance & Repairs",
            "Home Improvement & Renovations",
            "Lawn Care & Landscaping",
            "Home Services (cleaning, pest control, etc.)",
            "Furniture & Housewares",
            "Appliances",
        ],
    },
    "Transportation": {
        "type": "expense",
        "subcategories": [
            "Auto Loan / Lease Payment",
            "Gas & Fuel",
            "Auto Insurance",
            "Auto Maintenance & Repairs",
            "Tires & Auto Parts",
            "Car Wash & Detailing",
            "Parking & Tolls",
            "Vehicle Registration & DMV Fees",
            "Public Transit",
            "Taxi & Ride Shares",
            "Bike / Scooter Share Programs",
            "Roadside Assistance & Warranty",
        ],
    },
    "Utilities": {
        "type": "expense",
        "subcategories": [
            "Electricity",
            "Natural Gas",
            "Water & Sewer",
            "Garbage & Recycling",
            "Internet",
            "Cable & Television",
            "Phone (Mobile & Landline)",
            "Streaming Subscriptions",
            "Subscriptions & Memberships",
        ],
    },
    "Food & Dining": {
        "type": "expense",
        "subcategories": [
            "Groceries",
            "Restaurants & Bars",
            "Fast Food",
            "Coffee Shops & Cafes",
            "Food Delivery & Takeout",
            "Alcohol & Tobacco",
            "Snacks & Convenience Stores",
        ],
    },
    "Shopping": {
        "type": "expense",
        "subcategories": [
            "Clothing & Apparel",
            "Shoes & Accessories",
            "Jewelry",
            "Electronics & Gadgets",
            "Books, Music & Media",
            "Household Supplies",
            "Tools & Hardware",
        ],
    },
    "Personal Care": {
        "type": "expense",
        "subcategories": [
            "Toiletries & Personal Hygiene",
            "Beauty & Cosmetics",
            "Haircuts & Salon Services",
            "Spa, Massage & Wellness Treatments",
            "Dry Cleaning & Laundry",
            "Personal Care Services",
        ],
    },
    "Health & Wellness": {
        "type": "expense",
        "subcategories": [
            "Health Insurance",
            "Medical & Doctor Visits",
            "Prescriptions & Medications",
            "Pharmacy / Over-the-Counter",
            "Dentist & Dental Care",
            "Vision Care / Eyeglasses / Contacts",
            "Therapy & Mental Health",
            "Hospital / Urgent Care / Emergency",
            "Medical Devices & Supplies",
            "Supplements & Vitamins",
            "Alternative Medicine",
        ],
    },
    "Fitness & Recreation": {
        "type": "expense",
        "subcategories": [
            "Fitness / Gym Memberships",
            "Fitness Classes & Equipment",
            "Sports & Recreation",
        ],
    },
    "Travel & Vacation": {
        "type": "expense",
        "subcategories": [
            "Travel & Vacation",
            "Flights & Airfare",
            "Hotels & Lodging",
            "Rental Cars & Travel Transportation",
            "Travel Meals & Activities",
            "Souvenirs & Travel Gifts",
        ],
    },
    "Entertainment & Lifestyle": {
        "type": "expense",
        "subcategories": [
            "Entertainment & Recreation",
            "Movies, Theater & Concerts",
            "Video Games & Gaming",
            "Hobbies & Crafts",
            "Fun Money / Pocket Spending",
            "Sporting Events",
        ],
    },
    "Children & Family": {
        "type": "expense",
        "subcategories": [
            "Childcare / Daycare",
            "Children's Clothing & Shoes",
            "Child Activities / Sports / Lessons",
            "School Fees & Supplies",
            "Toys & Baby Supplies",
            "Allowance / Kids' Spending",
            "Child Support / Alimony Paid",
        ],
    },
    "Education": {
        "type": "expense",
        "subcategories": [
            "Student Loans",
            "Tuition & Education Fees",
            "Books & Educational Supplies",
            "Professional Development / Courses",
        ],
    },
    "Pets": {
        "type": "expense",
        "subcategories": [
            "Pet Food & Supplies",
            "Veterinary Care & Pet Medical",
            "Pet Grooming & Boarding",
            "Pet Insurance",
            "Pet Toys & Accessories",
        ],
    },
    "Gifts & Donations": {
        "type": "expense",
        "subcategories": [
            "Charity & Donations",
            "Religious Contributions",
            "Gifts Given",
        ],
    },
    "Financial & Debt": {
        "type": "expense",
        "subcategories": [
            "Loan Repayment (Non-Auto/Student)",
            "Financial & Legal Services",
            "Financial Fees",
            "Bank & Credit Card Fees",
            "Investment Fees",
            "Cash & ATM Withdrawals",
            "Taxes (Income, Property, etc.)",
            "Accountant / Tax Preparation",
        ],
    },
    "Business Expenses": {
        "type": "expense",
        "subcategories": [
            "Advertising & Promotion",
            "Business Utilities & Communication",
            "Employee Wages & Contract Labor",
            "Business Travel & Meals",
            "Business Auto Expenses",
            "Business Insurance",
            "Office Supplies & Expenses",
            "Office Rent",
            "Postage & Shipping",
            "Business Software & Tools",
            "Professional Services (legal, accounting)",
            "Business Licenses & Permits",
            "Marketing & Client Entertainment",
        ],
    },
    "Transfers & Adjustments": {
        "type": "transfer",
        "subcategories": [
            "Internal Transfer",
            "Savings Contributions",
            "Investment Contributions",
            "Retirement Contributions",
            "Credit Card Payment",
            "Balance Adjustments",
        ],
    },
    "Other": {
        "type": "expense",
        "subcategories": [
            "Uncategorized",
            "Check",
            "Miscellaneous",
        ],
    },
}

# Budget definitions use category names; IDs are looked up at seed time.
_DEFAULT_BUDGETS = [
    {"id": "b1", "household_id": 1, "category_name": "Groceries",              "allocated": Decimal("400.00"), "color": "#66BB6A"},
    {"id": "b2", "household_id": 1, "category_name": "Restaurants & Bars",     "allocated": Decimal("200.00"), "color": "#FFA726"},
    {"id": "b3", "household_id": 1, "category_name": "Gas & Fuel",             "allocated": Decimal("150.00"), "color": "#42A5F5"},
    {"id": "b4", "household_id": 1, "category_name": "Entertainment & Recreation", "allocated": Decimal("100.00"), "color": "#AB47BC"},
    {"id": "b5", "household_id": 1, "category_name": "Household Supplies",     "allocated": Decimal("150.00"), "color": "#EC407A"},
    {"id": "b6", "household_id": 1, "category_name": "Medical & Doctor Visits","allocated": Decimal("100.00"), "color": "#EF5350"},
    {"id": "b7", "household_id": 1, "category_name": "Fitness / Gym Memberships", "allocated": Decimal("50.00"), "color": "#26A69A"},
]


async def seed_categories() -> None:
    """Insert default system categories with canonical stable IDs.

    Canonical ID = sort_order + 1 (1-based). IDs are assigned explicitly so
    every fresh deployment gets the same ID for every system category —
    Flutter clients can cache the category list indefinitely.

    Safe to re-run: categories already present (by name) are skipped.
    After inserting, the PostgreSQL sequence is reset to 144 so that
    user-created custom categories start from a non-conflicting value.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CategoryModel.name))
        existing = {name for (name,) in result.all()}

        added = 0
        sort_order = 0
        for group_name, group in _DEFAULT_CATEGORY_GROUPS.items():
            cat_type = group["type"]
            for name in group["subcategories"]:
                canonical_id = sort_order + 1
                if name not in existing:
                    db.add(
                        CategoryModel(
                            id=canonical_id,
                            name=name,
                            group_name=group_name,
                            type=cat_type,
                            is_system=True,
                            sort_order=sort_order,
                        )
                    )
                    added += 1
                sort_order += 1

        if added:
            await db.commit()
            # Reset sequence so custom categories never collide with system IDs.
            await db.execute(sa.text("SELECT setval('categories_id_seq', 143)"))
            await db.commit()
            logger.info("seeded default categories", count=added)


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
                logger.warning("budget skipped — unknown category", category_name=row["category_name"])
                continue
            db.add(BudgetModel(
                id=row["id"],
                household_id=row["household_id"],
                category_id=category_id,
                allocated=row["allocated"],
                color=row["color"],
            ))

        await db.commit()
        logger.info("seeded default budgets", count=len(_DEFAULT_BUDGETS))


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
        logger.info("seeded demo accounts", count=len(accounts))


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
                "category": "Fitness / Gym Memberships",
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
                "category": "Business Software & Tools",
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
                "category": "Internet",
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
        logger.info("seeded demo subscriptions", count=len(subscriptions))


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
            logger.warning("transaction CSV not found", csv_path=csv_path)
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
            logger.info("seeded transactions from CSV", count=len(transactions))
        except Exception:
            logger.exception("failed to load transactions from CSV")
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
        logger.info("seeded account snapshots", count=181)
