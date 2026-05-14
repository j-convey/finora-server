from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.models.transaction import Transaction
from app.infrastructure.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Transaction, db)

    async def get_by_id(self, transaction_id: str) -> Transaction | None:
        """Fetch a single transaction by primary key."""
        return await self.db.get(Transaction, transaction_id)

    async def get_by_id_for_household(
        self,
        transaction_id: str,
        household_id: int,
        *,
        for_update: bool = False,
    ) -> Transaction | None:
        """Tenant-scoped lookup. Returns None if missing or owned by a different household.

        Returns 404-safe None instead of raising so callers (routers) retain
        control over the HTTP response. Never returns 403 — always 404 — to
        prevent IDOR information leakage.
        """
        stmt = select(Transaction).where(Transaction.id == transaction_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        txn = result.scalar_one_or_none()
        if txn is None or txn.household_id != household_id:
            return None
        return txn

    async def list_with_category(
        self,
        *,
        subscription_id: str | None = None,
    ) -> list[Transaction]:
        """Return transactions with category_rel eagerly loaded, newest first."""
        stmt = (
            select(Transaction)
            .options(selectinload(Transaction.category_rel))
            .order_by(Transaction.date.desc())
        )
        if subscription_id is not None:
            stmt = stmt.where(Transaction.subscription_id == subscription_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
