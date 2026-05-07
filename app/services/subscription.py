from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.transaction import Transaction


@dataclass
class SubscriptionFilters:
    status: SubscriptionStatus | None = None
    upcoming_only: bool = False


class SubscriptionService:
    """Repository/service layer for subscription records and tx linking.

    Matching strategy is intentionally simple for Phase 1. Automatic linking is
    not enabled yet, but methods here are ready for future auto-matching hooks.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_subscription(self, household_id: int, data: dict[str, Any]) -> Subscription:
        subscription = Subscription(household_id=household_id, **data)
        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def find_by_id(self, subscription_id: str, household_id: int) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.household_id == household_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_all_for_user(
        self,
        household_id: int,
        filters: SubscriptionFilters | None = None,
    ) -> list[Subscription]:
        stmt = select(Subscription).where(Subscription.household_id == household_id)
        if filters:
            if filters.status is not None:
                stmt = stmt.where(Subscription.status == filters.status)
            if filters.upcoming_only:
                stmt = stmt.where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.next_due_date.is_not(None),
                    )
                )

        stmt = stmt.order_by(Subscription.next_due_date.asc().nulls_last(), Subscription.name.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_subscription(
        self,
        subscription_id: str,
        household_id: int,
        data: dict[str, Any],
    ) -> Subscription | None:
        subscription = await self.find_by_id(subscription_id, household_id)
        if subscription is None:
            return None

        for key, value in data.items():
            setattr(subscription, key, value)

        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def delete_subscription(
        self,
        subscription_id: str,
        household_id: int,
        soft_delete: bool = True,
    ) -> bool:
        subscription = await self.find_by_id(subscription_id, household_id)
        if subscription is None:
            return False

        if soft_delete:
            subscription.status = SubscriptionStatus.CANCELED
        else:
            await self.db.delete(subscription)

        await self.db.flush()
        return True

    async def link_transaction(
        self,
        transaction_id: str,
        subscription_id: str,
        household_id: int,
    ) -> Transaction | None:
        # Ownership check is anchored to subscription.household_id.
        subscription = await self.find_by_id(subscription_id, household_id)
        if subscription is None:
            return None

        tx = await self.db.get(Transaction, transaction_id)
        if tx is None:
            return None

        tx.subscription_id = subscription_id
        await self.db.flush()
        await self.db.refresh(tx)
        return tx

    async def unlink_transaction(self, transaction_id: str, household_id: int) -> Transaction | None:
        tx = await self.db.get(Transaction, transaction_id)
        if tx is None:
            return None

        if tx.subscription_id:
            subscription = await self.find_by_id(tx.subscription_id, household_id)
            if subscription is None:
                return None

        tx.subscription_id = None
        await self.db.flush()
        await self.db.refresh(tx)
        return tx

    async def find_active_subscriptions_for_user(self, household_id: int) -> list[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .where(
                Subscription.household_id == household_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .order_by(Subscription.name.asc())
        )
        return list(result.scalars().all())

    async def suggest_from_transactions(self, household_id: int, min_occurrences: int = 3) -> list[dict[str, Any]]:
        """Build coarse subscription suggestions from historical transactions.

        This helper is intended for admin tooling/backfill scripts, not runtime
        auto-linking. It groups by merchant_name then title and suggests records
        with repeated occurrences.
        """
        tx_result = await self.db.execute(
            select(Transaction).where(
                Transaction.type == "expense",
                Transaction.subscription_id.is_(None),
                or_(Transaction.merchant_name.is_not(None), Transaction.title.is_not(None)),
            )
        )
        transactions = tx_result.scalars().all()

        grouped: dict[str, list[Transaction]] = defaultdict(list)
        for tx in transactions:
            key = (tx.merchant_name or tx.title or "").strip().lower()
            if not key:
                continue
            grouped[key].append(tx)

        suggestions: list[dict[str, Any]] = []
        for _, items in grouped.items():
            if len(items) < min_occurrences:
                continue
            amounts = [Decimal(i.amount) for i in items]
            merchant = items[0].merchant_name or items[0].title
            suggestions.append(
                {
                    "household_id": household_id,
                    "name": merchant,
                    "merchant_name": merchant,
                    "count": len(items),
                    "min_amount": float(min(amounts)),
                    "max_amount": float(max(amounts)),
                    "sample_transaction_ids": [i.id for i in items[:5]],
                }
            )

        suggestions.sort(key=lambda s: s["count"], reverse=True)
        return suggestions
