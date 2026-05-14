from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.user import User
from app.infrastructure.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(User, db)

    async def list_by_household(self, household_id: int) -> list[User]:
        """Return all users belonging to a household."""
        result = await self.db.execute(
            select(User).where(User.household_id == household_id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_id_for_household(
        self, user_id: int, household_id: int
    ) -> User | None:
        """Tenant-scoped lookup. Returns None if the user doesn't belong to the household."""
        result = await self.db.execute(
            select(User).where(
                User.id == user_id, User.household_id == household_id
            )
        )
        return result.scalars().first()
