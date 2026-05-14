from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.category import Category
from app.infrastructure.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Category, db)

    async def list_names(self) -> list[str]:
        """Return all category names ordered by sort_order then name."""
        result = await self.db.execute(
            select(Category.name).order_by(Category.sort_order, Category.name)
        )
        return [name for (name,) in result.all()]

    async def resolve_id_by_name(self, name: str) -> int | None:
        """Return the category ID for a given name (case-insensitive), or None."""
        result = await self.db.execute(
            select(Category.id).where(
                func.lower(Category.name) == name.strip().lower()
            )
        )
        return result.scalar_one_or_none()

    async def load_name_to_id_map(self, *, system_only: bool = True) -> dict[str, int]:
        """Return a lowercase name → id mapping for all (or system-only) categories."""
        stmt = select(Category.id, Category.name)
        if system_only:
            stmt = stmt.where(Category.household_id.is_(None))
        result = await self.db.execute(stmt)
        return {name.lower(): cat_id for cat_id, name in result.all()}
