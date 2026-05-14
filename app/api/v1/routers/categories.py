from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.infrastructure.models.user import User
from app.infrastructure.repositories.category_repository import CategoryRepository

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
    return await CategoryRepository(db).list_names()
