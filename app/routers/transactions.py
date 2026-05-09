from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List

from app.core.database import get_db
from app.models.category import Category as CategoryModel
from app.models.subscription import Subscription as SubscriptionModel
from app.models.transaction import Transaction as TransactionModel
from app.schemas.transaction import Transaction, TransactionUpdate, SplitRequest

router = APIRouter()


def _days_ago(n: int) -> datetime:
    return (datetime.now(tz=timezone.utc) - timedelta(days=n)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _to_response(r: TransactionModel) -> Transaction:
    """Convert a TransactionModel ORM row to the API response schema.
    
    Category name is resolved from the joined category_rel relationship.
    """
    category_name = r.category_rel.name if r.category_rel else None
    return Transaction(
        id=r.id,
        title=r.title,
        original_description=r.original_description,
        merchant_name=r.merchant_name,
        provider_transaction_id=r.provider_transaction_id,
        amount=r.amount,
        type=r.type,
        category=category_name,
        provider_category=r.provider_category,
        date=r.date,
        pending=r.pending,
        account_id=r.account_id,
        subscription_id=r.subscription_id,
        notes=r.notes,
        is_split_parent=r.is_split_parent,
        parent_transaction_id=r.parent_transaction_id,
        requires_user_review=r.requires_user_review,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def _resolve_category_id(db: AsyncSession, name: str) -> int:
    """Look up a category by name (case-insensitive) and return its ID.

    Raises HTTPException(400) if the category does not exist.
    """
    candidate = name.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="Category cannot be empty")

    result = await db.execute(
        select(CategoryModel.id).where(
            func.lower(CategoryModel.name) == candidate.lower()
        )
    )
    cat_id = result.scalar_one_or_none()
    if cat_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {candidate!r}",
        )
    return cat_id


@router.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    subscription_id: str | None = Query(None, description="Optional subscription filter"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TransactionModel).options(selectinload(TransactionModel.category_rel))
    if subscription_id:
        stmt = stmt.where(TransactionModel.subscription_id == subscription_id)

    result = await db.execute(stmt.order_by(TransactionModel.date.desc()))
    rows = result.scalars().all()
    return [_to_response(r) for r in rows]


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
            txn.category_id = None
        else:
            txn.category_id = await _resolve_category_id(db, value)

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
    await db.refresh(txn, attribute_names=['category_rel'])

    return _to_response(txn)


@router.post("/transactions/{transaction_id}/split", response_model=List[Transaction])
async def split_transaction(
    transaction_id: str,
    body: SplitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Split a transaction into two or more categorised child transactions.

    Rules:
    - Requires at least 2 split entries.
    - The sum of split amounts must exactly equal the parent's amount.
    - Children inherit date, account_id, and provider_transaction_id from the parent.
    - The parent row is mutated to is_split_parent=True (excluded from budget queries).
    - The entire operation is atomic: any failure rolls back all changes.
    """
    parent = await db.get(TransactionModel, transaction_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if parent.is_split_parent:
        raise HTTPException(
            status_code=400,
            detail="Transaction is already split. Delete existing splits first.",
        )
    if parent.parent_transaction_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot split a child split transaction.",
        )

    entries = body.splits
    if len(entries) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 split entries are required.",
        )

    total = sum(e.amount for e in entries)
    if total != parent.amount:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Split amounts sum to {total} but parent amount is {parent.amount}. "
                "They must match exactly."
            ),
        )

    # Resolve category IDs upfront so we fail before mutating anything
    category_ids: list[int | None] = []
    for entry in entries:
        if entry.category:
            category_ids.append(await _resolve_category_id(db, entry.category))
        else:
            category_ids.append(parent.category_id)

    # Mutate parent — must happen before children are created
    parent.is_split_parent = True
    parent.requires_user_review = False
    db.add(parent)

    children: list[TransactionModel] = []
    for entry, cat_id in zip(entries, category_ids):
        child = TransactionModel(
            id=f"split_{uuid.uuid4().hex[:12]}",
            title=entry.title,
            original_description=parent.original_description,
            merchant_name=parent.merchant_name,
            provider_transaction_id=parent.provider_transaction_id,
            amount=entry.amount,
            type=parent.type,
            category_id=cat_id,
            provider_category=parent.provider_category,
            date=parent.date,
            pending=parent.pending,
            account_id=parent.account_id,
            subscription_id=None,
            notes=entry.notes,
            is_split_parent=False,
            parent_transaction_id=parent.id,
            requires_user_review=False,
        )
        db.add(child)
        children.append(child)

    await db.commit()

    # Refresh to pick up DB-generated timestamps, then eagerly load category_rel
    # (must be explicit — lazy loading is forbidden in async context).
    await db.refresh(parent)
    for child in children:
        await db.refresh(child)
        await db.refresh(child, attribute_names=['category_rel'])

    return [_to_response(c) for c in children]


@router.delete("/transactions/{transaction_id}/split", status_code=204)
async def unsplit_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove all child splits from a parent transaction, restoring it to a normal row.

    The parent's is_split_parent flag is cleared and all children are deleted
    (CASCADE handles this at the DB level, but we also clear the flag explicitly).
    """
    parent = await db.get(TransactionModel, transaction_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not parent.is_split_parent:
        raise HTTPException(status_code=400, detail="Transaction has no splits to remove.")

    # Load children and delete them explicitly so SQLAlchemy fires CASCADE correctly
    result = await db.execute(
        select(TransactionModel).where(
            TransactionModel.parent_transaction_id == transaction_id
        )
    )
    for child in result.scalars().all():
        await db.delete(child)

    parent.is_split_parent = False
    parent.requires_user_review = False
    db.add(parent)

    await db.commit()
