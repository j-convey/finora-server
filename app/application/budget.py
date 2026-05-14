"""
Budget service — business logic layer.

Keeps the router thin: all DB queries and domain rules live here.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.budget import Budget as BudgetModel
from app.infrastructure.repositories.budget_repository import BudgetRepository
from app.infrastructure.repositories.category_repository import CategoryRepository
from app.api.v1.schemas.budget import Budget, BudgetCreate, BudgetUpdate


async def _resolve_category_id(db: AsyncSession, name: str) -> int:
    """Resolve a category name to its ID. Raises 400 if not found."""
    cat_id = await CategoryRepository(db).resolve_id_by_name(name)
    if cat_id is None:
        raise HTTPException(status_code=400, detail=f"Unknown category: {name!r}")
    return cat_id


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
    budget_repo = BudgetRepository(db)
    rows = await budget_repo.list_with_category()
    budgets = []
    for row in rows:
        spent = await budget_repo.compute_spent(row.category_id)
        budgets.append(_to_schema(row, spent))
    return sorted(budgets, key=lambda b: b.category)


async def get_budget(db: AsyncSession, budget_id: str) -> Optional[Budget]:
    budget_repo = BudgetRepository(db)
    row = await budget_repo.get_by_id(budget_id)
    if not row:
        return None
    await db.refresh(row, attribute_names=['category_rel'])
    spent = await budget_repo.compute_spent(row.category_id)
    return _to_schema(row, spent)


async def create_budget(db: AsyncSession, data: BudgetCreate) -> Budget:
    budget_repo = BudgetRepository(db)
    category_id = await _resolve_category_id(db, data.category)
    model = BudgetModel(
        household_id=1,
        category_id=category_id,
        allocated=data.allocated,
        color=data.color,
    )
    db.add(model)
    await db.flush()
    spent = await budget_repo.compute_spent(model.category_id)
    await db.commit()
    await db.refresh(model)
    await db.refresh(model, attribute_names=['category_rel'])
    return _to_schema(model, spent)


async def update_budget(
    db: AsyncSession, budget_id: str, data: BudgetUpdate
) -> Optional[Budget]:
    budget_repo = BudgetRepository(db)
    row = await budget_repo.get_by_id(budget_id)
    if not row:
        return None
    if data.allocated is not None:
        row.allocated = data.allocated
    if data.color is not None:
        row.color = data.color
    await db.commit()
    await db.refresh(row)
    await db.refresh(row, attribute_names=['category_rel'])
    spent = await budget_repo.compute_spent(row.category_id)
    return _to_schema(row, spent)


async def delete_budget(db: AsyncSession, budget_id: str) -> bool:
    row = await BudgetRepository(db).get_by_id(budget_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
