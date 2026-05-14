from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.models.budget import Budget
from app.infrastructure.models.transaction import Transaction
from app.infrastructure.repositories.base import BaseRepository


class BudgetRepository(BaseRepository[Budget]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Budget, db)

    async def list_with_category(self) -> list[Budget]:
        """Return all budgets with category_rel eagerly loaded."""
        result = await self.db.execute(
            select(Budget).options(selectinload(Budget.category_rel))
        )
        return list(result.scalars().all())

    async def get_by_id(self, budget_id: str) -> Budget | None:
        return await self.db.get(Budget, budget_id)

    async def compute_spent(self, category_id: int) -> Decimal:
        """Sum expense transaction amounts for a category in the current calendar month (UTC).

        Excludes split-parent ghost rows so amounts are never double-counted.
        """
        now = datetime.now(tz=timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.amount), Decimal("0.0000"))
            ).where(
                Transaction.category_id == category_id,
                Transaction.type == "expense",
                Transaction.date >= month_start,
                Transaction.is_split_parent == False,  # noqa: E712
            )
        )
        return Decimal(str(result.scalar()))
