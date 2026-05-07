"""
Budget service — business logic layer.

Keeps the router thin: all DB queries and domain rules live here.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget as BudgetModel
from app.models.transaction import Transaction as TransactionModel
from app.schemas.budget import Budget, BudgetCreate, BudgetUpdate


async def _compute_spent(db: AsyncSession, category: str) -> Decimal:
    """
    Sum all expense transactions for *category* in the current calendar month (UTC).
    Returns Decimal("0.0000") when there are no matching transactions.
    """
    now = datetime.now(tz=timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.coalesce(func.sum(TransactionModel.amount), Decimal("0.0000"))).where(
            TransactionModel.category == category,
            TransactionModel.type == "expense",
            TransactionModel.date >= month_start,
        )
    )
    return Decimal(str(result.scalar()))


def _to_schema(model: BudgetModel, spent: float) -> Budget:
    return Budget(
        id=model.id,
        category=model.category,
        allocated=model.allocated,
        color=model.color,
        spent=spent,
    )


async def list_budgets(db: AsyncSession) -> list[Budget]:
    result = await db.execute(select(BudgetModel).order_by(BudgetModel.category))
    rows = result.scalars().all()
    budgets = []
    for row in rows:
        spent = await _compute_spent(db, row.category)
        budgets.append(_to_schema(row, spent))
    return budgets


async def get_budget(db: AsyncSession, budget_id: str) -> Optional[Budget]:
    row = await db.get(BudgetModel, budget_id)
    if not row:
        return None
    spent = await _compute_spent(db, row.category)
    return _to_schema(row, spent)


async def create_budget(db: AsyncSession, data: BudgetCreate) -> Budget:
    model = BudgetModel(
        category=data.category,
        allocated=data.allocated,
        color=data.color,
    )
    db.add(model)
    await db.flush()  # get generated id before commit
    spent = await _compute_spent(db, model.category)
    await db.commit()
    await db.refresh(model)
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
    spent = await _compute_spent(db, row.category)
    return _to_schema(row, spent)


async def delete_budget(db: AsyncSession, budget_id: str) -> bool:
    row = await db.get(BudgetModel, budget_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
