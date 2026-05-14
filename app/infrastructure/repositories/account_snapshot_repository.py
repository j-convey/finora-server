from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.account_snapshot import AccountSnapshot
from app.infrastructure.repositories.base import BaseRepository


class AccountSnapshotRepository(BaseRepository[AccountSnapshot]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(AccountSnapshot, db)

    async def get_by_household_and_date(
        self, household_id: int, snapshot_date: date
    ) -> AccountSnapshot | None:
        """Fetch an existing snapshot for a household on a specific date."""
        result = await self.db.execute(
            select(AccountSnapshot).where(
                and_(
                    AccountSnapshot.household_id == household_id,
                    AccountSnapshot.snapshot_date == snapshot_date,
                )
            )
        )
        return result.scalars().first()

    async def get_history(
        self, household_id: int, start_date: date, end_date: date
    ) -> list[AccountSnapshot]:
        """Return snapshots for a household within an inclusive date range, oldest first."""
        result = await self.db.execute(
            select(AccountSnapshot)
            .where(
                and_(
                    AccountSnapshot.household_id == household_id,
                    AccountSnapshot.snapshot_date >= start_date,
                    AccountSnapshot.snapshot_date <= end_date,
                )
            )
            .order_by(AccountSnapshot.snapshot_date)
        )
        return list(result.scalars().all())
