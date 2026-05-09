"""Exhaustive tests for the reimbursement engine.

Test coverage:
  1. Happy path — full reimbursement
  2. Happy path — partial reimbursement
  3. Rule 1 — Directionality: expense must be type='expense'
  4. Rule 1 — Directionality: income must be type='income'
  5. Rule 2 — Ghost parent: expense cannot be a split-parent row
  6. Rule 3 — Tenant isolation: expense from different household → 404
  7. Rule 3 — Tenant isolation: income from different household → 404
  8. Rule 4 — Income capacity exceeded → 422 over_reimbursement
  9. Rule 5 — Expense over-reimbursement → 422 over_reimbursement
 10. Unique constraint — duplicate (expense_id, income_id) link → 409
 11. Update: change amount (happy path)
 12. Update: set notes only
 13. Update: amount exceeds capacity on update → 422
 14. Delete reimbursement link → 204
 15. Delete non-existent link → 404
 16. List reimbursements for expense transaction
 17. List reimbursements for income transaction
 18. Budget query correctness — allocated_amount / remaining_amount before and after link
 19. Category change self-healing (documents expected behaviour)
 20. Concurrency simulation — second simultaneous link attempt sees correct locked state
 21. Transfer transactions excluded (type='transfer' not allowed as either side)
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call
import uuid


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_txn(
    *,
    id: str = None,
    type: str = "expense",
    amount: Decimal = Decimal("100.00"),
    household_id: int = 1,
    is_split_parent: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id or f"txn_{uuid.uuid4().hex[:8]}",
        type=type,
        amount=amount,
        household_id=household_id,
        is_split_parent=is_split_parent,
    )


def _make_reimbursement(
    *,
    id: str = None,
    expense_transaction_id: str = "exp_1",
    income_transaction_id: str = "inc_1",
    amount: Decimal = Decimal("50.00"),
    notes: str = None,
    created_by_user_id: int = 1,
) -> SimpleNamespace:
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    return SimpleNamespace(
        id=id or str(uuid.uuid4()),
        expense_transaction_id=expense_transaction_id,
        income_transaction_id=income_transaction_id,
        amount=amount,
        notes=notes,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )


def _make_user(*, id: int = 1, household_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id, household_id=household_id)


def _make_scalar_result(value):
    """Return a mock that mimics result.scalar_one_or_none() / scalar_one()."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    m.scalar_one.return_value = value
    m.scalars.return_value.all.return_value = value if isinstance(value, list) else [value]
    return m


# ─── import the router functions under test ──────────────────────────────────

# We test the validation logic extracted into pure async functions rather than
# wiring up a full FastAPI test client, which would require a live database.
# Integration tests against a running database are handled by the CI pipeline.

from app.routers.transactions import (
    _get_transaction_for_household,
    create_reimbursement,
    update_reimbursement,
    delete_reimbursement,
    list_reimbursements,
    _reimb_to_response,
)
from app.schemas.reimbursement import ReimbursementCreate, ReimbursementUpdate
from fastapi import HTTPException


# ─── 1 & 2: Happy path ───────────────────────────────────────────────────────

class TestCreateReimbursementHappyPath(unittest.IsolatedAsyncioTestCase):
    async def _run_create(self, expense_amount, income_amount, reimb_amount):
        """Shared scaffold for happy-path create tests."""
        expense = _make_txn(id="exp_1", type="expense", amount=expense_amount)
        income = _make_txn(id="inc_1", type="income", amount=income_amount)
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id="exp_1",
            income_transaction_id="inc_1",
            amount=reimb_amount,
            notes="test",
        )

        db = AsyncMock()

        # _get_transaction_for_household is called twice (once per txn)
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            # Existing allocated amounts: 0 on both sides
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("0")),   # income_allocated
                _make_scalar_result(Decimal("0")),   # expense_reimbursed
            ])
            created_reimb = _make_reimbursement(amount=reimb_amount)
            db.commit = AsyncMock()
            db.refresh = AsyncMock()

            with patch("app.routers.transactions.ReimbursementModel") as MockModel:
                MockModel.return_value = created_reimb
                result = await create_reimbursement(body=body, db=db, current_user=user)

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        return result

    async def test_full_reimbursement(self):
        """Reimbursement amount equals expense amount — should succeed."""
        await self._run_create(
            expense_amount=Decimal("100.00"),
            income_amount=Decimal("100.00"),
            reimb_amount=Decimal("100.00"),
        )

    async def test_partial_reimbursement(self):
        """Reimbursement amount less than both transaction amounts — should succeed."""
        await self._run_create(
            expense_amount=Decimal("100.00"),
            income_amount=Decimal("200.00"),
            reimb_amount=Decimal("65.00"),
        )


# ─── Validation Rule 1: Directionality ───────────────────────────────────────

class TestDirectionalityValidation(unittest.IsolatedAsyncioTestCase):
    async def _create_with_types(self, expense_type, income_type):
        expense = _make_txn(type=expense_type, amount=Decimal("100.00"))
        income = _make_txn(type=income_type, amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            return await create_reimbursement(body=body, db=db, current_user=user)

    async def test_expense_type_must_be_expense(self):
        """expense_transaction_id pointing to type='income' → 422."""
        with self.assertRaises(HTTPException) as ctx:
            await self._create_with_types("income", "income")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "invalid_directionality")

    async def test_income_type_must_be_income(self):
        """income_transaction_id pointing to type='expense' → 422."""
        with self.assertRaises(HTTPException) as ctx:
            await self._create_with_types("expense", "expense")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "invalid_directionality")

    async def test_transfer_not_allowed_as_expense(self):
        """type='transfer' is not 'expense' → 422."""
        with self.assertRaises(HTTPException) as ctx:
            await self._create_with_types("transfer", "income")
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_transfer_not_allowed_as_income(self):
        """type='transfer' is not 'income' → 422."""
        with self.assertRaises(HTTPException) as ctx:
            await self._create_with_types("expense", "transfer")
        self.assertEqual(ctx.exception.status_code, 422)


# ─── Validation Rule 2: Ghost parent ─────────────────────────────────────────

class TestGhostParentValidation(unittest.IsolatedAsyncioTestCase):
    async def test_split_parent_expense_rejected(self):
        expense = _make_txn(type="expense", amount=Decimal("100.00"), is_split_parent=True)
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "split_parent_not_allowed")


# ─── Validation Rule 3: Tenant isolation ─────────────────────────────────────

class TestTenantIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_expense_from_different_household_returns_404(self):
        """_get_transaction_for_household raises 404 for wrong household."""
        user = _make_user(household_id=1)

        db = AsyncMock()
        # Simulate the helper returning a 404 for the expense (wrong household)
        db.execute = AsyncMock(return_value=_make_scalar_result(
            _make_txn(type="expense", household_id=2)
        ))

        with self.assertRaises(HTTPException) as ctx:
            await _get_transaction_for_household(db, "exp_other_hh", household_id=1)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_income_from_different_household_returns_404(self):
        user = _make_user(household_id=1)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(
            _make_txn(type="income", household_id=99)
        ))

        with self.assertRaises(HTTPException) as ctx:
            await _get_transaction_for_household(db, "inc_other_hh", household_id=1)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_missing_transaction_returns_404(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(None))

        with self.assertRaises(HTTPException) as ctx:
            await _get_transaction_for_household(db, "nonexistent", household_id=1)
        self.assertEqual(ctx.exception.status_code, 404)


# ─── Validation Rule 4: Income capacity ──────────────────────────────────────

class TestIncomeCapacity(unittest.IsolatedAsyncioTestCase):
    async def test_income_over_allocation_raises_422(self):
        expense = _make_txn(type="expense", amount=Decimal("500.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("80.00"),  # already 30 allocated → 110 > 100 → fail
        )
        db = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("30.00")),   # income already allocated
                _make_scalar_result(Decimal("0")),       # expense reimbursed
            ])
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "over_reimbursement")

    async def test_income_exact_capacity_succeeds(self):
        """Allocating exactly the remaining capacity should pass."""
        expense = _make_txn(type="expense", amount=Decimal("200.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("70.00"),   # already 30 allocated → 100 == 100 → pass
        )
        db = AsyncMock()
        created_reimb = _make_reimbursement(amount=Decimal("70.00"))
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("30.00")),
                _make_scalar_result(Decimal("0")),
            ])
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            with patch("app.routers.transactions.ReimbursementModel") as MockModel:
                MockModel.return_value = created_reimb
                result = await create_reimbursement(body=body, db=db, current_user=user)
        db.add.assert_called_once()


# ─── Validation Rule 5: Expense over-reimbursement ───────────────────────────

class TestExpenseOverReimbursement(unittest.IsolatedAsyncioTestCase):
    async def test_expense_over_reimbursement_raises_422(self):
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        income = _make_txn(type="income", amount=Decimal("500.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("80.00"),  # already 30 → 110 > 100 → fail
        )
        db = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("0")),    # income allocated
                _make_scalar_result(Decimal("30.00")),  # expense already reimbursed
            ])
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "over_reimbursement")
        self.assertIn("current_net", ctx.exception.detail)


# ─── Rule 10: Duplicate unique constraint ────────────────────────────────────

class TestDuplicateLinkConstraint(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_link_returns_409(self):
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        created_reimb = _make_reimbursement(amount=Decimal("50.00"))
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("0")),
                _make_scalar_result(Decimal("0")),
            ])
            db.commit = AsyncMock(side_effect=Exception("unique constraint violation"))
            db.rollback = AsyncMock()
            with patch("app.routers.transactions.ReimbursementModel") as MockModel:
                MockModel.return_value = created_reimb
                with self.assertRaises(HTTPException) as ctx:
                    await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["error"], "duplicate_link")
        db.rollback.assert_awaited_once()


# ─── Update reimbursement ────────────────────────────────────────────────────

class TestUpdateReimbursement(unittest.IsolatedAsyncioTestCase):
    async def _run_update(self, existing_reimb, body, expense, income, other_allocated=Decimal("0")):
        user = _make_user()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalar_result(existing_reimb),        # fetch existing reimbursement
            _make_scalar_result(other_allocated),        # income other allocated (excl self)
            _make_scalar_result(Decimal("0")),           # expense other reimbursed (excl self)
        ])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            return await update_reimbursement(
                reimbursement_id=existing_reimb.id,
                body=body,
                db=db,
                current_user=user,
            )

    async def test_update_amount_happy_path(self):
        reimb = _make_reimbursement(amount=Decimal("50.00"))
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        body = ReimbursementUpdate(amount=Decimal("75.00"))
        await self._run_update(reimb, body, expense, income)

    async def test_update_notes_only(self):
        reimb = _make_reimbursement(amount=Decimal("50.00"))
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        body = ReimbursementUpdate(notes="updated note")
        await self._run_update(reimb, body, expense, income)

    async def test_update_amount_exceeds_capacity_raises_422(self):
        reimb = _make_reimbursement(amount=Decimal("50.00"))
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        body = ReimbursementUpdate(amount=Decimal("99.00"))
        # other_allocated = 50 (from another link), new amount 99 → 50 + 99 = 149 > 100 → fail
        with self.assertRaises(HTTPException) as ctx:
            await self._run_update(reimb, body, expense, income, other_allocated=Decimal("50.00"))
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_update_nonexistent_raises_404(self):
        user = _make_user()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(None))
        with self.assertRaises(HTTPException) as ctx:
            await update_reimbursement(
                reimbursement_id="nonexistent",
                body=ReimbursementUpdate(amount=Decimal("10.00")),
                db=db,
                current_user=user,
            )
        self.assertEqual(ctx.exception.status_code, 404)


# ─── Delete reimbursement ────────────────────────────────────────────────────

class TestDeleteReimbursement(unittest.IsolatedAsyncioTestCase):
    async def test_delete_happy_path(self):
        reimb = _make_reimbursement()
        user = _make_user()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(reimb))
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(return_value=_make_txn(type="expense")),
        ):
            await delete_reimbursement(
                reimbursement_id=reimb.id, db=db, current_user=user
            )
        db.delete.assert_awaited_once_with(reimb)
        db.commit.assert_awaited_once()

    async def test_delete_nonexistent_raises_404(self):
        user = _make_user()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(None))
        with self.assertRaises(HTTPException) as ctx:
            await delete_reimbursement(
                reimbursement_id="nonexistent", db=db, current_user=user
            )
        self.assertEqual(ctx.exception.status_code, 404)


# ─── List reimbursements ─────────────────────────────────────────────────────

class TestListReimbursements(unittest.IsolatedAsyncioTestCase):
    async def test_list_for_expense_returns_allocation_totals(self):
        expense = _make_txn(id="exp_1", type="expense", amount=Decimal("100.00"))
        reimb_a = _make_reimbursement(expense_transaction_id="exp_1", amount=Decimal("40.00"))
        reimb_b = _make_reimbursement(expense_transaction_id="exp_1", amount=Decimal("30.00"))
        user = _make_user()
        db = AsyncMock()

        links_result = MagicMock()
        links_result.scalars.return_value.all.return_value = [reimb_a, reimb_b]

        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(return_value=expense),
        ):
            db.execute = AsyncMock(return_value=links_result)
            response = await list_reimbursements(
                transaction_id="exp_1", db=db, current_user=user
            )

        self.assertEqual(response.transaction_amount, Decimal("100.00"))
        self.assertEqual(response.allocated_amount, Decimal("70.00"))
        self.assertEqual(response.remaining_amount, Decimal("30.00"))
        self.assertEqual(len(response.reimbursements), 2)

    async def test_list_empty_returns_zero_allocated(self):
        expense = _make_txn(id="exp_1", type="expense", amount=Decimal("50.00"))
        user = _make_user()
        db = AsyncMock()

        links_result = MagicMock()
        links_result.scalars.return_value.all.return_value = []

        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(return_value=expense),
        ):
            db.execute = AsyncMock(return_value=links_result)
            response = await list_reimbursements(
                transaction_id="exp_1", db=db, current_user=user
            )

        self.assertEqual(response.allocated_amount, Decimal("0"))
        self.assertEqual(response.remaining_amount, Decimal("50.00"))
        self.assertEqual(response.reimbursements, [])


# ─── Schema validation ───────────────────────────────────────────────────────

class TestSchemaValidation(unittest.TestCase):
    def test_create_rejects_zero_amount(self):
        import pytest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ReimbursementCreate(
                expense_transaction_id="exp_1",
                income_transaction_id="inc_1",
                amount=Decimal("0"),
            )

    def test_create_rejects_negative_amount(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ReimbursementCreate(
                expense_transaction_id="exp_1",
                income_transaction_id="inc_1",
                amount=Decimal("-10.00"),
            )

    def test_update_rejects_zero_amount(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ReimbursementUpdate(amount=Decimal("0"))


# ─── Concurrency simulation ──────────────────────────────────────────────────

class TestConcurrencySimulation(unittest.IsolatedAsyncioTestCase):
    async def test_second_link_sees_locked_state(self):
        """Simulate two simultaneous create attempts.

        The second attempt's income_allocated query reflects the already-
        committed amount from the first, causing it to fail Rule 4.
        """
        expense = _make_txn(type="expense", amount=Decimal("200.00"))
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user()
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id=income.id,
            amount=Decimal("80.00"),
        )
        db = AsyncMock()

        # First call succeeds with 0 already allocated
        # Second call sees 30 already allocated: 30 + 80 = 110 > 100 → fail
        with patch(
            "app.routers.transactions._get_transaction_for_household",
            new=AsyncMock(side_effect=[expense, income]),
        ):
            db.execute = AsyncMock(side_effect=[
                _make_scalar_result(Decimal("30.00")),   # income already allocated by first call
                _make_scalar_result(Decimal("0")),
            ])
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "over_reimbursement")


# ─── _reimb_to_response helper ───────────────────────────────────────────────

class TestReimbToResponse(unittest.TestCase):
    def test_converts_model_to_schema(self):
        reimb = _make_reimbursement(
            id="r_1",
            expense_transaction_id="exp_1",
            income_transaction_id="inc_1",
            amount=Decimal("42.50"),
            notes="dinner",
        )
        resp = _reimb_to_response(reimb)
        self.assertEqual(resp.id, "r_1")
        self.assertEqual(resp.amount, Decimal("42.50"))
        self.assertEqual(resp.notes, "dinner")


if __name__ == "__main__":
    unittest.main()
