from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.models.category import Category as CategoryModel
from app.models.subscription import Subscription as SubscriptionModel
from app.models.transaction import Transaction as TransactionModel
from app.schemas.transaction import Transaction, TransactionUpdate

router = APIRouter()


def _days_ago(n: int) -> datetime:
    return (datetime.now(tz=timezone.utc) - timedelta(days=n)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _seed() -> List[Transaction]:
    return [
        Transaction(id="t1",  title="Monthly Salary",     amount=5200.00, type="income",  category="Income",        date=_days_ago(1),  account_id="a1", notes=None),
        Transaction(id="t2",  title="Whole Foods Market", amount=87.43,   type="expense", category="Groceries",     date=_days_ago(2),  account_id="a1", notes=None),
        Transaction(id="t3",  title="Netflix",            amount=15.99,   type="expense", category="Subscriptions", date=_days_ago(3),  account_id="a1", notes=None),
        Transaction(id="t4",  title="Uber Ride",          amount=18.50,   type="expense", category="Transport",     date=_days_ago(3),  account_id="a1", notes=None),
        Transaction(id="t5",  title="Freelance Payment",  amount=850.00,  type="income",  category="Income",        date=_days_ago(5),  account_id="a1", notes=None),
        Transaction(id="t6",  title="Chipotle",           amount=14.75,   type="expense", category="Dining",        date=_days_ago(5),  account_id="a1", notes=None),
        Transaction(id="t7",  title="Rent",               amount=1800.00, type="expense", category="Rent",          date=_days_ago(7),  account_id="a1", notes=None),
        Transaction(id="t8",  title="Spotify",            amount=9.99,    type="expense", category="Subscriptions", date=_days_ago(8),  account_id="a1", notes=None),
        Transaction(id="t9",  title="Gym Membership",     amount=45.00,   type="expense", category="Health",        date=_days_ago(10), account_id="a1", notes=None),
        Transaction(id="t10", title="Electric Bill",      amount=92.30,   type="expense", category="Utilities",     date=_days_ago(12), account_id="a1", notes=None),
        Transaction(id="t11", title="Amazon Order",       amount=67.99,   type="expense", category="Shopping",      date=_days_ago(14), account_id="a1", notes=None),
        Transaction(id="t12", title="Trader Joe's",       amount=54.20,   type="expense", category="Groceries",     date=_days_ago(15), account_id="a1", notes=None),
        Transaction(id="t13", title="Investment Dividend",amount=320.00,  type="income",  category="Income",        date=_days_ago(17), account_id="a4", notes=None),
        Transaction(id="t14", title="Movie Theater",      amount=28.50,   type="expense", category="Entertainment", date=_days_ago(18), account_id="a1", notes=None),
        Transaction(id="t15", title="Doctor Copay",       amount=35.00,   type="expense", category="Health",        date=_days_ago(20), account_id="a1", notes=None),
    ]


@router.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    subscription_id: str | None = Query(None, description="Optional subscription filter"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TransactionModel)
    if subscription_id:
        stmt = stmt.where(TransactionModel.subscription_id == subscription_id)

    result = await db.execute(stmt.order_by(TransactionModel.date.desc()))
    rows = result.scalars().all()
    return [
        Transaction(
            id=r.id,
            title=r.title,
            original_description=r.original_description,
            merchant_name=r.merchant_name,
            provider_transaction_id=r.provider_transaction_id,
            amount=r.amount,
            type=r.type,
            category=r.category,
            provider_category=r.provider_category,
            date=r.date,
            pending=r.pending,
            account_id=r.account_id,
            subscription_id=r.subscription_id,
            notes=r.notes,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


async def _resolve_category_name(db: AsyncSession, name: str) -> str:
    """Look up a category case-insensitively and return its canonical name.

    Raises HTTPException(400) if the category does not exist.
    """
    candidate = name.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="Category cannot be empty")

    result = await db.execute(
        select(CategoryModel.name).where(
            func.lower(CategoryModel.name) == candidate.lower()
        )
    )
    canonical = result.scalar_one_or_none()
    if canonical is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {candidate!r}",
        )
    return canonical


@router.patch("/transactions/{transaction_id}", response_model=Transaction)
async def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    txn = await db.get(TransactionModel, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    updates = body.model_dump(exclude_unset=True)

    if "category" in updates:
        value = updates["category"]
        if value is None:
            txn.category = None
        else:
            txn.category = await _resolve_category_name(db, value)

    if "title" in updates and updates["title"] is not None:
        txn.title = updates["title"]

    if "subscription_id" in updates:
        sub_id = updates["subscription_id"]
        if sub_id is None:
            txn.subscription_id = None
        else:
            subscription = await db.get(SubscriptionModel, sub_id)
            if subscription is None:
                raise HTTPException(status_code=400, detail="Unknown subscription_id")
            txn.subscription_id = sub_id

    if "notes" in updates:
        txn.notes = updates["notes"]

    await db.commit()
    await db.refresh(txn)

    return Transaction(
        id=txn.id,
        title=txn.title,
        original_description=txn.original_description,
        merchant_name=txn.merchant_name,
        provider_transaction_id=txn.provider_transaction_id,
        amount=txn.amount,
        type=txn.type,
        category=txn.category,
        provider_category=txn.provider_category,
        date=txn.date,
        pending=txn.pending,
        account_id=txn.account_id,
        subscription_id=txn.subscription_id,
        notes=txn.notes,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
    )
