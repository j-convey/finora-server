from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.category import Category as CategoryModel
from app.models.subscription import Subscription as SubscriptionModel
from app.models.transaction import Transaction as TransactionModel
from app.models.transaction_reimbursement import TransactionReimbursement as ReimbursementModel
from app.models.user import User
from app.schemas.transaction import Transaction, TransactionUpdate, SplitRequest
from app.schemas.reimbursement import (
    ReimbursementCreate,
    ReimbursementListResponse,
    ReimbursementResponse,
    ReimbursementUpdate,
)

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


# ─────────────────────────────────────────────────────────────────────────────
# Reimbursement endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _reimb_to_response(r: ReimbursementModel) -> ReimbursementResponse:
    return ReimbursementResponse(
        id=r.id,
        expense_transaction_id=r.expense_transaction_id,
        income_transaction_id=r.income_transaction_id,
        amount=r.amount,
        notes=r.notes,
        created_by_user_id=r.created_by_user_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def _get_transaction_for_household(
    db: AsyncSession,
    transaction_id: str,
    household_id: int,
    *,
    for_update: bool = False,
) -> TransactionModel:
    """Fetch a transaction and verify it belongs to the caller's household.

    Returns 404 (not 403) for any missing or out-of-household transaction to
    prevent IDOR information leakage.
    """
    stmt = select(TransactionModel).where(TransactionModel.id == transaction_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    txn = result.scalar_one_or_none()
    if txn is None or txn.household_id != household_id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.post(
    "/transactions/reimbursements",
    response_model=ReimbursementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link an income transaction as a (partial) reimbursement of an expense",
)
async def create_reimbursement(
    body: ReimbursementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReimbursementResponse:
    """Create a reimbursement link between an expense and an income transaction.

    All five validation rules run atomically with row-level locks to prevent
    race conditions. Returns 422 with a structured error body on capacity
    violations, and 404 for any tenant-isolation failure.
    """
    # Row-level locks on both transactions prevent concurrent double-allocation.
    expense_txn = await _get_transaction_for_household(
        db, body.expense_transaction_id, current_user.household_id, for_update=True
    )
    income_txn = await _get_transaction_for_household(
        db, body.income_transaction_id, current_user.household_id, for_update=True
    )

    # Rule 1 – Directionality: expense must be type='expense', income must be type='income'
    if expense_txn.type != "expense":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_directionality",
                "message": "expense_transaction_id must point to a transaction with type='expense'",
            },
        )
    if income_txn.type != "income":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_directionality",
                "message": "income_transaction_id must point to a transaction with type='income'",
            },
        )

    # Rule 2 – Ghost parent: expense cannot be a split-parent ghost row
    if expense_txn.is_split_parent:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "split_parent_not_allowed",
                "message": "Cannot reimburse a split-parent transaction. Link the individual split children instead.",
            },
        )

    # Rule 4 – Income capacity: sum of existing allocations + new amount <= income amount
    income_allocated_result = await db.execute(
        select(func.coalesce(func.sum(ReimbursementModel.amount), Decimal("0")))
        .where(ReimbursementModel.income_transaction_id == income_txn.id)
    )
    income_allocated: Decimal = income_allocated_result.scalar_one()
    if income_allocated + body.amount > income_txn.amount:
        over_by = float((income_allocated + body.amount - income_txn.amount))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "over_reimbursement",
                "message": f"This would over-allocate the income transaction by ${over_by:.2f}",
                "allocated_amount": float(income_allocated),
                "max_allowed": float(income_txn.amount - income_allocated),
            },
        )

    # Rule 5 – Expense over-reimbursement: sum of existing + new <= expense amount
    expense_reimbursed_result = await db.execute(
        select(func.coalesce(func.sum(ReimbursementModel.amount), Decimal("0")))
        .where(ReimbursementModel.expense_transaction_id == expense_txn.id)
    )
    expense_reimbursed: Decimal = expense_reimbursed_result.scalar_one()
    if expense_reimbursed + body.amount > expense_txn.amount:
        over_by = float((expense_reimbursed + body.amount - expense_txn.amount))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "over_reimbursement",
                "message": f"This would over-reimburse the expense by ${over_by:.2f}",
                "current_net": float(expense_txn.amount - expense_reimbursed),
                "max_allowed": float(expense_txn.amount - expense_reimbursed),
            },
        )

    reimbursement = ReimbursementModel(
        id=str(uuid.uuid4()),
        expense_transaction_id=expense_txn.id,
        income_transaction_id=income_txn.id,
        amount=body.amount,
        notes=body.notes,
        created_by_user_id=current_user.id,
    )
    db.add(reimbursement)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # The unique constraint (expense_id, income_id) was violated — already linked.
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_link",
                "message": "A reimbursement link between these two transactions already exists. Update the existing link instead.",
            },
        )

    await db.refresh(reimbursement)
    return _reimb_to_response(reimbursement)


@router.put(
    "/transactions/reimbursements/{reimbursement_id}",
    response_model=ReimbursementResponse,
    summary="Update the amount or notes on an existing reimbursement link",
)
async def update_reimbursement(
    reimbursement_id: str,
    body: ReimbursementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReimbursementResponse:
    """Update amount and/or notes on an existing reimbursement.

    Re-validates capacity rules (Rules 4 & 5) using the updated amount so the
    system stays consistent. Row-level locks are acquired on both transactions.
    """
    result = await db.execute(
        select(ReimbursementModel).where(ReimbursementModel.id == reimbursement_id)
    )
    reimbursement = result.scalar_one_or_none()
    if reimbursement is None:
        raise HTTPException(status_code=404, detail="Reimbursement not found")

    # Verify household ownership for both transactions (tenant isolation)
    expense_txn = await _get_transaction_for_household(
        db, reimbursement.expense_transaction_id, current_user.household_id, for_update=True
    )
    income_txn = await _get_transaction_for_household(
        db, reimbursement.income_transaction_id, current_user.household_id, for_update=True
    )

    new_amount = body.amount if body.amount is not None else reimbursement.amount

    # Re-validate capacity excluding this reimbursement's own current amount
    income_allocated_result = await db.execute(
        select(func.coalesce(func.sum(ReimbursementModel.amount), Decimal("0")))
        .where(
            ReimbursementModel.income_transaction_id == income_txn.id,
            ReimbursementModel.id != reimbursement_id,
        )
    )
    income_allocated: Decimal = income_allocated_result.scalar_one()
    if income_allocated + new_amount > income_txn.amount:
        over_by = float((income_allocated + new_amount - income_txn.amount))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "over_reimbursement",
                "message": f"This would over-allocate the income transaction by ${over_by:.2f}",
                "allocated_amount": float(income_allocated),
                "max_allowed": float(income_txn.amount - income_allocated),
            },
        )

    expense_reimbursed_result = await db.execute(
        select(func.coalesce(func.sum(ReimbursementModel.amount), Decimal("0")))
        .where(
            ReimbursementModel.expense_transaction_id == expense_txn.id,
            ReimbursementModel.id != reimbursement_id,
        )
    )
    expense_reimbursed: Decimal = expense_reimbursed_result.scalar_one()
    if expense_reimbursed + new_amount > expense_txn.amount:
        over_by = float((expense_reimbursed + new_amount - expense_txn.amount))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "over_reimbursement",
                "message": f"This would over-reimburse the expense by ${over_by:.2f}",
                "current_net": float(expense_txn.amount - expense_reimbursed),
                "max_allowed": float(expense_txn.amount - expense_reimbursed),
            },
        )

    if body.amount is not None:
        reimbursement.amount = new_amount
    if body.notes is not None:
        reimbursement.notes = body.notes

    await db.commit()
    await db.refresh(reimbursement)
    return _reimb_to_response(reimbursement)


@router.delete(
    "/transactions/reimbursements/{reimbursement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a reimbursement link",
)
async def delete_reimbursement(
    reimbursement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a reimbursement link. Budget queries recalculate dynamically."""
    result = await db.execute(
        select(ReimbursementModel).where(ReimbursementModel.id == reimbursement_id)
    )
    reimbursement = result.scalar_one_or_none()
    if reimbursement is None:
        raise HTTPException(status_code=404, detail="Reimbursement not found")

    # Verify the caller's household owns at least the expense transaction
    await _get_transaction_for_household(
        db, reimbursement.expense_transaction_id, current_user.household_id
    )

    await db.delete(reimbursement)
    await db.commit()


@router.get(
    "/transactions/{transaction_id}/reimbursements",
    response_model=ReimbursementListResponse,
    summary="List reimbursement links for a transaction (expense or income side)",
)
async def list_reimbursements(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReimbursementListResponse:
    """Return all reimbursement links where this transaction appears on either side.

    The response includes allocated_amount and remaining_amount computed from
    the live database state so the client can render capacity indicators without
    a second request.
    """
    txn = await _get_transaction_for_household(db, transaction_id, current_user.household_id)

    # Fetch links where this transaction is either the expense or the income side
    stmt = select(ReimbursementModel).where(
        (ReimbursementModel.expense_transaction_id == transaction_id)
        | (ReimbursementModel.income_transaction_id == transaction_id)
    ).order_by(ReimbursementModel.created_at.asc())
    result = await db.execute(stmt)
    links = result.scalars().all()

    allocated_amount = sum((r.amount for r in links), Decimal("0"))
    remaining_amount = max(txn.amount - allocated_amount, Decimal("0"))

    return ReimbursementListResponse(
        transaction_id=transaction_id,
        transaction_amount=txn.amount,
        allocated_amount=allocated_amount,
        remaining_amount=remaining_amount,
        reimbursements=[_reimb_to_response(r) for r in links],
    )

