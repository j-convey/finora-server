"""
Budget service — business logic layer.

Keeps the router thin: all DB queries and domain rules live here.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget as BudgetModel
from app.models.category import Category as CategoryModel
from app.models.transaction import Transaction as TransactionModel
from app.schemas.budget import Budget, BudgetCreate, BudgetUpdate


async def _resolve_category_id(db: AsyncSession, name: str) -> int:
    """Resolve a category name to its ID. Raises 400 if not found."""
    result = await db.execute(
        select(CategoryModel.id).where(
            func.lower(CategoryModel.name) == name.strip().lower()
        )
    )
    cat_id = result.scalar_one_or_none()
    if cat_id is None:
        raise HTTPException(status_code=400, detail=f"Unknown category: {name!r}")
    return cat_id


async def _compute_spent(db: AsyncSession, category_id: int) -> Decimal:
    """Sum all expense transactions for category_id in the current calendar month (UTC)."""
    now = datetime.now(tz=timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.coalesce(func.sum(TransactionModel.amount), Decimal("0.0000"))).where(
            TransactionModel.category_id == category_id,
            TransactionModel.type == "expense",
            TransactionModel.date >= month_start,
            # Rule B: exclude ghost parent rows — only count leaf/unsplit transactions
            TransactionModel.is_split_parent == False,  # noqa: E712
        )
    )
    return Decimal(str(result.scalar()))


def _to_schema(model: BudgetModel, spent: Decimal) -> Budget:
    category_name = model.category_rel.name if model.category_rel else ""
    return Budget(
        id=model.id,
        category=category_name,
        allocated=model.allocated,
        color=model.color,
        spent=spent,
    )


async def list_budgets(db: AsyncSession) -> list[Budget]:
    result = await db.execute(
        select(BudgetModel).options(selectinload(BudgetModel.category_rel))
    )
    rows = result.scalars().all()
    budgets = []
    for row in rows:
        spent = await _compute_spent(db, row.category_id)
        budgets.append(_to_schema(row, spent))
    return sorted(budgets, key=lambda b: b.category)


async def get_budget(db: AsyncSession, budget_id: str) -> Optional[Budget]:
    row = await db.get(BudgetModel, budget_id)
    if not row:
        return None
    await db.refresh(row, attribute_names=['category_rel'])
    spent = await _compute_spent(db, row.category_id)
    return _to_schema(row, spent)


async def create_budget(db: AsyncSession, data: BudgetCreate) -> Budget:
    category_id = await _resolve_category_id(db, data.category)
    model = BudgetModel(
        household_id=1,
        category_id=category_id,
        allocated=data.allocated,
        color=data.color,
    )
    db.add(model)
    await db.flush()
    spent = await _compute_spent(db, model.category_id)
    await db.commit()
    await db.refresh(model)
    await db.refresh(model, attribute_names=['category_rel'])
    return _to_schema(model, spent)


async def update_budget(
    db: AsyncSession, budget_id: str, data: BudgetUpdate
) -> Optional[Budget]:
    row = await db.get(BudgetModel, budget_id)
    if not row:
        return None
    if data.allocated is not None:
        row.allocated = data.allocated
    if data.color is not None:
        row.color = data.color
    await db.commit()
    await db.refresh(row)
    await db.refresh(row, attribute_names=['category_rel'])
    spent = await _compute_spent(db, row.category_id)
    return _to_schema(row, spent)


async def delete_budget(db: AsyncSession, budget_id: str) -> bool:
    row = await db.get(BudgetModel, budget_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
