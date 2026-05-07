import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.models.subscription import SubscriptionStatus
from app.services.subscription import SubscriptionService


class SubscriptionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_subscription_assigns_user(self):
        db = AsyncMock()
        service = SubscriptionService(db)

        created = await service.create_subscription(
            user_id=1,
            data={"name": "Netflix", "recurrence_interval": 1, "recurrence_unit": "month"},
        )

        self.assertEqual(created.user_id, 1)
        self.assertEqual(created.name, "Netflix")
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_link_transaction_fails_when_subscription_not_owned(self):
        db = AsyncMock()
        service = SubscriptionService(db)
        service.find_by_id = AsyncMock(return_value=None)

        result = await service.link_transaction("tx_1", "sub_1", user_id=42)

        self.assertIsNone(result)

    async def test_unlink_transaction_clears_subscription(self):
        tx = SimpleNamespace(id="tx_1", subscription_id="sub_1")
        db = AsyncMock()
        db.get = AsyncMock(return_value=tx)

        service = SubscriptionService(db)
        service.find_by_id = AsyncMock(return_value=SimpleNamespace(id="sub_1", user_id=1))

        updated = await service.unlink_transaction("tx_1", user_id=1)

        self.assertIsNotNone(updated)
        self.assertIsNone(updated.subscription_id)
        db.flush.assert_awaited_once()

    async def test_find_active_subscriptions_for_user(self):
        db = AsyncMock()
        expected = [SimpleNamespace(id="sub_1", status=SubscriptionStatus.ACTIVE)]
        scalars = AsyncMock()
        scalars.all.return_value = expected
        result_obj = AsyncMock()
        result_obj.scalars.return_value = scalars
        db.execute.return_value = result_obj

        service = SubscriptionService(db)
        result = await service.find_active_subscriptions_for_user(1)

        self.assertEqual(result, expected)
        db.execute.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
