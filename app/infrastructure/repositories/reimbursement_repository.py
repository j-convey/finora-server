from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.transaction_reimbursement import TransactionReimbursement
from app.infrastructure.repositories.base import BaseRepository


class ReimbursementRepository(BaseRepository[TransactionReimbursement]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(TransactionReimbursement, db)

    async def get_by_id(self, reimbursement_id: str) -> TransactionReimbursement | None:
        result = await self.db.execute(
            select(TransactionReimbursement).where(
                TransactionReimbursement.id == reimbursement_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_transaction(
        self, transaction_id: str
    ) -> list[TransactionReimbursement]:
        """Return all reimbursement links where the transaction appears on either side."""
        result = await self.db.execute(
            select(TransactionReimbursement)
            .where(
                (TransactionReimbursement.expense_transaction_id == transaction_id)
                | (TransactionReimbursement.income_transaction_id == transaction_id)
            )
            .order_by(TransactionReimbursement.created_at.asc())
        )
        return list(result.scalars().all())

    async def sum_allocated_to_income(
        self,
        income_transaction_id: str,
        *,
        exclude_id: str | None = None,
    ) -> Decimal:
        """Sum of amounts already allocated against a given income transaction.

        Pass ``exclude_id`` when re-validating an update to exclude the row
        being edited from the running total.
        """
        stmt = select(
            func.coalesce(func.sum(TransactionReimbursement.amount), Decimal("0"))
        ).where(TransactionReimbursement.income_transaction_id == income_transaction_id)
        if exclude_id is not None:
            stmt = stmt.where(TransactionReimbursement.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def sum_reimbursed_from_expense(
        self,
        expense_transaction_id: str,
        *,
        exclude_id: str | None = None,
    ) -> Decimal:
        """Sum of amounts already reimbursed from a given expense transaction.

        Pass ``exclude_id`` when re-validating an update to exclude the row
        being edited from the running total.
        """
        stmt = select(
            func.coalesce(func.sum(TransactionReimbursement.amount), Decimal("0"))
        ).where(
            TransactionReimbursement.expense_transaction_id == expense_transaction_id
        )
        if exclude_id is not None:
            stmt = stmt.where(TransactionReimbursement.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()
