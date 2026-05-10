from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.category import Category as CategoryModel
from app.models.user import User

router = APIRouter()


@router.get("/categories", response_model=List[str])
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """Return the canonical list of transaction category names.

    Ordered by sort_order then name. Clients use this list as the only valid
    set of categories when creating or updating transactions.
    """
    result = await db.execute(
        select(CategoryModel.name).order_by(
            CategoryModel.sort_order, CategoryModel.name
        )
    )
    return [name for (name,) in result.all()]
