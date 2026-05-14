from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.account import Account
from app.infrastructure.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Account, db)

    async def list_all(self) -> list[Account]:
        """Return all accounts ordered by name."""
        result = await self.db.execute(select(Account).order_by(Account.name))
        return list(result.scalars().all())

    async def get_by_id(self, account_id: str) -> Account | None:
        return await self.db.get(Account, account_id)
