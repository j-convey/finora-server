from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.infrastructure.models.user import User
from app.infrastructure.repositories.category_repository import CategoryRepository
from app.api.v1.schemas.category import CategoryGroupResponse

router = APIRouter()


@router.get("/categories", response_model=List[CategoryGroupResponse])
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[CategoryGroupResponse]:
    """Return all transaction categories grouped by their category group.

    Each group includes the group name, its type (income / expense / transfer),
    and the ordered list of subcategory items, each with a stable canonical
    ``id`` and display ``name``.

    The ``id`` values for system categories are canonical and never change —
    clients may cache the full list and reference IDs long-term without
    re-fetching. Use the ``id`` when creating or updating a transaction's
    category (``category_id`` field).
    """
    rows = await CategoryRepository(db).list_grouped()
    return [CategoryGroupResponse(**row) for row in rows]
