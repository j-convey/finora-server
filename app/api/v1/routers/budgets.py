from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.auth import get_current_user
from app.core.database import get_db
from app.infrastructure.models.user import User
from app.api.v1.schemas.budget import Budget, BudgetCreate, BudgetUpdate
from app.application import budget as budget_service

router = APIRouter()


@router.get("/budgets", response_model=List[Budget])
async def get_budgets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all budgets with dynamically computed spent values for the current month."""
    return await budget_service.list_budgets(db)


@router.post("/budgets", response_model=Budget, status_code=status.HTTP_201_CREATED)
async def create_budget(
    body: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new budget envelope for a category."""
    return await budget_service.create_budget(db, body)


@router.patch("/budgets/{budget_id}", response_model=Budget)
async def update_budget(
    budget_id: str,
    body: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the allocated amount or color of an existing budget."""
    result = await budget_service.update_budget(db, budget_id, body)
    if not result:
        raise HTTPException(status_code=404, detail=f"Budget '{budget_id}' not found")
    return result


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a budget envelope."""
    deleted = await budget_service.delete_budget(db, budget_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Budget '{budget_id}' not found")

