"""Restructure categories: grouped hierarchy with type field.

Revision ID: 011_restructure_categories
Revises: 010_add_admin_flag
Create Date: 2026-05-15 00:00:00.000000

Changes:
  - categories.group_name (String, nullable) — top-level display group
  - categories.type (String, nullable) — "income" | "expense" | "transfer"
  - Replaces the old flat system category list with a grouped hierarchy.
  - All existing transaction.category_id values are reset to Uncategorized
    (ON DELETE SET NULL fires when old system rows are deleted; a subsequent
    UPDATE re-points those NULLs to the new Uncategorized id).
"""
from alembic import op
import sqlalchemy as sa

revision = "011_restructure_categories"
down_revision = "010_add_admin_flag"
branch_labels = None
depends_on = None

# Full category list: (name, group_name, type, sort_order)
_NEW_CATEGORIES = [
    # Income
    ("Paychecks", "Income", "income", 0),
    ("Bonuses & Commissions", "Income", "income", 1),
    ("Overtime", "Income", "income", 2),
    ("Business Income / Revenue", "Income", "income", 3),
    ("Freelance / Side Hustle Income", "Income", "income", 4),
    ("Self-Employment Income", "Income", "income", 5),
    ("Interest Income", "Income", "income", 6),
    ("Dividends & Investment Income", "Income", "income", 7),
    ("Rental Income", "Income", "income", 8),
    ("Pension / Retirement Income", "Income", "income", 9),
    ("Government Benefits (Social Security, etc.)", "Income", "income", 10),
    ("Tax Refunds & Credits", "Income", "income", 11),
    ("Reimbursements", "Income", "income", 12),
    ("Gifts Received", "Income", "income", 13),
    ("Alimony / Child Support Received", "Income", "income", 14),
    ("Other Income", "Income", "income", 15),
    # Housing
    ("Mortgage", "Housing", "expense", 16),
    ("Rent", "Housing", "expense", 17),
    ("Property Taxes", "Housing", "expense", 18),
    ("HOA / Condo Fees", "Housing", "expense", 19),
    ("Homeowners / Renters Insurance", "Housing", "expense", 20),
    ("Home Maintenance & Repairs", "Housing", "expense", 21),
    ("Home Improvement & Renovations", "Housing", "expense", 22),
    ("Lawn Care & Landscaping", "Housing", "expense", 23),
    ("Home Services (cleaning, pest control, etc.)", "Housing", "expense", 24),
    ("Furniture & Housewares", "Housing", "expense", 25),
    ("Appliances", "Housing", "expense", 26),
    # Transportation
    ("Auto Loan / Lease Payment", "Transportation", "expense", 27),
    ("Gas & Fuel", "Transportation", "expense", 28),
    ("Auto Insurance", "Transportation", "expense", 29),
    ("Auto Maintenance & Repairs", "Transportation", "expense", 30),
    ("Tires & Auto Parts", "Transportation", "expense", 31),
    ("Car Wash & Detailing", "Transportation", "expense", 32),
    ("Parking & Tolls", "Transportation", "expense", 33),
    ("Vehicle Registration & DMV Fees", "Transportation", "expense", 34),
    ("Public Transit", "Transportation", "expense", 35),
    ("Taxi & Ride Shares", "Transportation", "expense", 36),
    ("Bike / Scooter Share Programs", "Transportation", "expense", 37),
    ("Roadside Assistance & Warranty", "Transportation", "expense", 38),
    # Utilities
    ("Electricity", "Utilities", "expense", 39),
    ("Natural Gas", "Utilities", "expense", 40),
    ("Water & Sewer", "Utilities", "expense", 41),
    ("Garbage & Recycling", "Utilities", "expense", 42),
    ("Internet", "Utilities", "expense", 43),
    ("Cable & Television", "Utilities", "expense", 44),
    ("Phone (Mobile & Landline)", "Utilities", "expense", 45),
    ("Streaming Subscriptions", "Utilities", "expense", 46),
    ("Subscriptions & Memberships", "Utilities", "expense", 47),
    # Food & Dining
    ("Groceries", "Food & Dining", "expense", 48),
    ("Restaurants & Bars", "Food & Dining", "expense", 49),
    ("Fast Food", "Food & Dining", "expense", 50),
    ("Coffee Shops & Cafes", "Food & Dining", "expense", 51),
    ("Food Delivery & Takeout", "Food & Dining", "expense", 52),
    ("Alcohol & Tobacco", "Food & Dining", "expense", 53),
    ("Snacks & Convenience Stores", "Food & Dining", "expense", 54),
    # Shopping
    ("Clothing & Apparel", "Shopping", "expense", 55),
    ("Shoes & Accessories", "Shopping", "expense", 56),
    ("Jewelry", "Shopping", "expense", 57),
    ("Electronics & Gadgets", "Shopping", "expense", 58),
    ("Books, Music & Media", "Shopping", "expense", 59),
    ("Household Supplies", "Shopping", "expense", 60),
    ("Tools & Hardware", "Shopping", "expense", 61),
    # Personal Care
    ("Toiletries & Personal Hygiene", "Personal Care", "expense", 62),
    ("Beauty & Cosmetics", "Personal Care", "expense", 63),
    ("Haircuts & Salon Services", "Personal Care", "expense", 64),
    ("Spa, Massage & Wellness Treatments", "Personal Care", "expense", 65),
    ("Dry Cleaning & Laundry", "Personal Care", "expense", 66),
    ("Personal Care Services", "Personal Care", "expense", 67),
    # Health & Wellness
    ("Health Insurance", "Health & Wellness", "expense", 68),
    ("Medical & Doctor Visits", "Health & Wellness", "expense", 69),
    ("Prescriptions & Medications", "Health & Wellness", "expense", 70),
    ("Pharmacy / Over-the-Counter", "Health & Wellness", "expense", 71),
    ("Dentist & Dental Care", "Health & Wellness", "expense", 72),
    ("Vision Care / Eyeglasses / Contacts", "Health & Wellness", "expense", 73),
    ("Therapy & Mental Health", "Health & Wellness", "expense", 74),
    ("Hospital / Urgent Care / Emergency", "Health & Wellness", "expense", 75),
    ("Medical Devices & Supplies", "Health & Wellness", "expense", 76),
    ("Supplements & Vitamins", "Health & Wellness", "expense", 77),
    ("Alternative Medicine", "Health & Wellness", "expense", 78),
    # Fitness & Recreation
    ("Fitness / Gym Memberships", "Fitness & Recreation", "expense", 79),
    ("Fitness Classes & Equipment", "Fitness & Recreation", "expense", 80),
    ("Sports & Recreation", "Fitness & Recreation", "expense", 81),
    # Travel & Vacation
    ("Travel & Vacation", "Travel & Vacation", "expense", 82),
    ("Flights & Airfare", "Travel & Vacation", "expense", 83),
    ("Hotels & Lodging", "Travel & Vacation", "expense", 84),
    ("Rental Cars & Travel Transportation", "Travel & Vacation", "expense", 85),
    ("Travel Meals & Activities", "Travel & Vacation", "expense", 86),
    ("Souvenirs & Travel Gifts", "Travel & Vacation", "expense", 87),
    # Entertainment & Lifestyle
    ("Entertainment & Recreation", "Entertainment & Lifestyle", "expense", 88),
    ("Movies, Theater & Concerts", "Entertainment & Lifestyle", "expense", 89),
    ("Video Games & Gaming", "Entertainment & Lifestyle", "expense", 90),
    ("Hobbies & Crafts", "Entertainment & Lifestyle", "expense", 91),
    ("Fun Money / Pocket Spending", "Entertainment & Lifestyle", "expense", 92),
    ("Sporting Events", "Entertainment & Lifestyle", "expense", 93),
    # Children & Family
    ("Childcare / Daycare", "Children & Family", "expense", 94),
    ("Children's Clothing & Shoes", "Children & Family", "expense", 95),
    ("Child Activities / Sports / Lessons", "Children & Family", "expense", 96),
    ("School Fees & Supplies", "Children & Family", "expense", 97),
    ("Toys & Baby Supplies", "Children & Family", "expense", 98),
    ("Allowance / Kids' Spending", "Children & Family", "expense", 99),
    ("Child Support / Alimony Paid", "Children & Family", "expense", 100),
    # Education
    ("Student Loans", "Education", "expense", 101),
    ("Tuition & Education Fees", "Education", "expense", 102),
    ("Books & Educational Supplies", "Education", "expense", 103),
    ("Professional Development / Courses", "Education", "expense", 104),
    # Pets
    ("Pet Food & Supplies", "Pets", "expense", 105),
    ("Veterinary Care & Pet Medical", "Pets", "expense", 106),
    ("Pet Grooming & Boarding", "Pets", "expense", 107),
    ("Pet Insurance", "Pets", "expense", 108),
    ("Pet Toys & Accessories", "Pets", "expense", 109),
    # Gifts & Donations
    ("Charity & Donations", "Gifts & Donations", "expense", 110),
    ("Religious Contributions", "Gifts & Donations", "expense", 111),
    ("Gifts Given", "Gifts & Donations", "expense", 112),
    # Financial & Debt
    ("Loan Repayment (Non-Auto/Student)", "Financial & Debt", "expense", 113),
    ("Financial & Legal Services", "Financial & Debt", "expense", 114),
    ("Financial Fees", "Financial & Debt", "expense", 115),
    ("Bank & Credit Card Fees", "Financial & Debt", "expense", 116),
    ("Investment Fees", "Financial & Debt", "expense", 117),
    ("Cash & ATM Withdrawals", "Financial & Debt", "expense", 118),
    ("Taxes (Income, Property, etc.)", "Financial & Debt", "expense", 119),
    ("Accountant / Tax Preparation", "Financial & Debt", "expense", 120),
    # Business Expenses
    ("Advertising & Promotion", "Business Expenses", "expense", 121),
    ("Business Utilities & Communication", "Business Expenses", "expense", 122),
    ("Employee Wages & Contract Labor", "Business Expenses", "expense", 123),
    ("Business Travel & Meals", "Business Expenses", "expense", 124),
    ("Business Auto Expenses", "Business Expenses", "expense", 125),
    ("Business Insurance", "Business Expenses", "expense", 126),
    ("Office Supplies & Expenses", "Business Expenses", "expense", 127),
    ("Office Rent", "Business Expenses", "expense", 128),
    ("Postage & Shipping", "Business Expenses", "expense", 129),
    ("Business Software & Tools", "Business Expenses", "expense", 130),
    ("Professional Services (legal, accounting)", "Business Expenses", "expense", 131),
    ("Business Licenses & Permits", "Business Expenses", "expense", 132),
    ("Marketing & Client Entertainment", "Business Expenses", "expense", 133),
    # Transfers & Adjustments
    ("Internal Transfer", "Transfers & Adjustments", "transfer", 134),
    ("Savings Contributions", "Transfers & Adjustments", "transfer", 135),
    ("Investment Contributions", "Transfers & Adjustments", "transfer", 136),
    ("Retirement Contributions", "Transfers & Adjustments", "transfer", 137),
    ("Credit Card Payment", "Transfers & Adjustments", "transfer", 138),
    ("Balance Adjustments", "Transfers & Adjustments", "transfer", 139),
    # Other
    ("Uncategorized", "Other", "expense", 140),
    ("Check", "Other", "expense", 141),
    ("Miscellaneous", "Other", "expense", 142),
]


def upgrade() -> None:
    # 1. Add the two new columns (nullable so existing rows are unaffected).
    op.add_column("categories", sa.Column("group_name", sa.String(), nullable=True))
    op.add_column("categories", sa.Column("type", sa.String(), nullable=True))
    op.create_index("ix_categories_group_name", "categories", ["group_name"])

    # 2. Delete all system categories.
    #    The FK on transactions.category_id has ON DELETE SET NULL, so the DB
    #    automatically NULLs every affected transaction.category_id here.
    op.execute(
        sa.text("DELETE FROM categories WHERE is_system = TRUE AND household_id IS NULL")
    )

    # 3. Insert the new grouped system categories.
    categories_table = sa.table(
        "categories",
        sa.column("name", sa.String()),
        sa.column("group_name", sa.String()),
        sa.column("type", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        # household_id intentionally omitted — defaults to NULL (system rows)
    )
    op.bulk_insert(
        categories_table,
        [
            {
                "name": name,
                "group_name": group_name,
                "type": cat_type,
                "is_system": True,
                "sort_order": sort_order,
            }
            for name, group_name, cat_type, sort_order in _NEW_CATEGORIES
        ],
    )

    # 4. Re-point any NULL'd transaction.category_id to the new Uncategorized.
    op.execute(
        sa.text("""
            UPDATE transactions
            SET category_id = (
                SELECT id FROM categories
                WHERE name = 'Uncategorized' AND household_id IS NULL
            )
            WHERE category_id IS NULL
        """)
    )


def downgrade() -> None:
    # Reset all transactions to NULL (safest — we can't reconstruct old IDs).
    op.execute(sa.text("UPDATE transactions SET category_id = NULL"))

    # Remove new system categories.
    op.execute(
        sa.text("DELETE FROM categories WHERE is_system = TRUE AND household_id IS NULL")
    )

    # Drop new index and columns.
    op.drop_index("ix_categories_group_name", table_name="categories")
    op.drop_column("categories", "type")
    op.drop_column("categories", "group_name")
