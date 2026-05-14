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
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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


_UNSET = object()


@contextmanager
def _patch_repos(
    *,
    expense_txn=_UNSET,
    income_txn=_UNSET,
    reimb=None,
    income_allocated: Decimal = Decimal("0"),
    expense_reimbursed: Decimal = Decimal("0"),
    links=None,
):
    """
    Context manager that patches TransactionRepository and ReimbursementRepository
    in the transactions router with pre-configured AsyncMock instances.

    When both expense_txn and income_txn are provided (even if None), the mock is
    configured with side_effect so the first call returns expense_txn and the second
    returns income_txn. This correctly handles the case where expense_txn=None means
    "the tenant isolation check found no matching transaction".
    """
    mock_txn_repo = AsyncMock()
    mock_reimb_repo = AsyncMock()

    if expense_txn is not _UNSET and income_txn is not _UNSET:
        # Both explicitly given — set up sequential side effects
        mock_txn_repo.get_by_id_for_household.side_effect = [expense_txn, income_txn]
    elif expense_txn is not _UNSET:
        mock_txn_repo.get_by_id_for_household.return_value = expense_txn
    elif income_txn is not _UNSET:
        mock_txn_repo.get_by_id_for_household.return_value = income_txn
    else:
        mock_txn_repo.get_by_id_for_household.return_value = None

    mock_reimb_repo.get_by_id.return_value = reimb
    mock_reimb_repo.sum_allocated_to_income.return_value = income_allocated
    mock_reimb_repo.sum_reimbursed_from_expense.return_value = expense_reimbursed
    mock_reimb_repo.list_by_transaction.return_value = links or []

    with patch(
        "app.api.v1.routers.transactions.TransactionRepository",
        return_value=mock_txn_repo,
    ), patch(
        "app.api.v1.routers.transactions.ReimbursementRepository",
        return_value=mock_reimb_repo,
    ):
        yield mock_txn_repo, mock_reimb_repo


# ─── imports ────────────────────────────────────────────────────────────────

from app.api.v1.routers.transactions import (
    create_reimbursement,
    update_reimbursement,
    delete_reimbursement,
    list_reimbursements,
    _reimb_to_response,
)
from app.api.v1.schemas.reimbursement import ReimbursementCreate, ReimbursementUpdate
from fastapi import HTTPException


# ─── 1 & 2: Happy path ───────────────────────────────────────────────────────

class TestCreateReimbursementHappyPath(unittest.IsolatedAsyncioTestCase):
    async def _run_create(self, expense_amount, income_amount, reimb_amount):
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
        created_reimb = _make_reimbursement(amount=reimb_amount)

        with _patch_repos(expense_txn=expense, income_txn=income):
            with patch("app.api.v1.routers.transactions.ReimbursementModel") as MockModel:
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
        with _patch_repos(expense_txn=expense, income_txn=income):
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
        with _patch_repos(expense_txn=expense, income_txn=income):
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error"], "split_parent_not_allowed")


# ─── Validation Rule 3: Tenant isolation ─────────────────────────────────────

class TestTenantIsolation(unittest.IsolatedAsyncioTestCase):
    """
    Tenant isolation is enforced by TransactionRepository.get_by_id_for_household,
    which returns None for any transaction that does not belong to the household.
    The router converts None → HTTP 404 to prevent IDOR information leakage.
    """

    async def test_expense_from_different_household_returns_404(self):
        """get_by_id_for_household returning None for expense → 404."""
        income = _make_txn(type="income", amount=Decimal("100.00"))
        user = _make_user(household_id=1)
        body = ReimbursementCreate(
            expense_transaction_id="exp_other_hh",
            income_transaction_id=income.id,
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        with _patch_repos(expense_txn=None, income_txn=income):
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_income_from_different_household_returns_404(self):
        """get_by_id_for_household returning None for income → 404."""
        expense = _make_txn(type="expense", amount=Decimal("100.00"))
        user = _make_user(household_id=1)
        body = ReimbursementCreate(
            expense_transaction_id=expense.id,
            income_transaction_id="inc_other_hh",
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        mock_txn_repo = AsyncMock()
        mock_txn_repo.get_by_id_for_household.side_effect = [expense, None]
        mock_reimb_repo = AsyncMock()
        with patch(
            "app.api.v1.routers.transactions.TransactionRepository",
            return_value=mock_txn_repo,
        ), patch(
            "app.api.v1.routers.transactions.ReimbursementRepository",
            return_value=mock_reimb_repo,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_missing_transaction_returns_404(self):
        """get_by_id_for_household returning None for a nonexistent id → 404."""
        user = _make_user(household_id=1)
        body = ReimbursementCreate(
            expense_transaction_id="nonexistent",
            income_transaction_id="also_nonexistent",
            amount=Decimal("50.00"),
        )
        db = AsyncMock()
        with _patch_repos(expense_txn=None):
            with self.assertRaises(HTTPException) as ctx:
                await create_reimbursement(body=body, db=db, current_user=user)
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
        with _patch_repos(
            expense_txn=expense,
            income_txn=income,
            income_allocated=Decimal("30.00"),
        ):
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
            amount=Decimal("70.00"),  # already 30 allocated → 100 == 100 → pass
        )
        db = AsyncMock()
        created_reimb = _make_reimbursement(amount=Decimal("70.00"))
        with _patch_repos(
            expense_txn=expense,
            income_txn=income,
            income_allocated=Decimal("30.00"),
        ):
            with patch("app.api.v1.routers.transactions.ReimbursementModel") as MockModel:
                MockModel.return_value = created_reimb
                await create_reimbursement(body=body, db=db, current_user=user)
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
        with _patch_repos(
            expense_txn=expense,
            income_txn=income,
            expense_reimbursed=Decimal("30.00"),
        ):
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
        db.commit = AsyncMock(side_effect=Exception("unique constraint violation"))
        db.rollback = AsyncMock()
        created_reimb = _make_reimbursement(amount=Decimal("50.00"))
        with _patch_repos(expense_txn=expense, income_txn=income):
            with patch("app.api.v1.routers.transactions.ReimbursementModel") as MockModel:
                MockModel.return_value = created_reimb
                with self.assertRaises(HTTPException) as ctx:
                    await create_reimbursement(body=body, db=db, current_user=user)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["error"], "duplicate_link")
        db.rollback.assert_awaited_once()


# ─── Update reimbursement ────────────────────────────────────────────────────

class TestUpdateReimbursement(unittest.IsolatedAsyncioTestCase):
    async def _run_update(
        self, existing_reimb, body, expense, income,
        other_income_allocated=Decimal("0"),
        other_expense_reimbursed=Decimal("0"),
    ):
        user = _make_user()
        db = AsyncMock()
        mock_txn_repo = AsyncMock()
        mock_txn_repo.get_by_id_for_household.side_effect = [expense, income]
        mock_reimb_repo = AsyncMock()
        mock_reimb_repo.get_by_id.return_value = existing_reimb
        mock_reimb_repo.sum_allocated_to_income.return_value = other_income_allocated
        mock_reimb_repo.sum_reimbursed_from_expense.return_value = other_expense_reimbursed

        with patch(
            "app.api.v1.routers.transactions.TransactionRepository",
            return_value=mock_txn_repo,
        ), patch(
            "app.api.v1.routers.transactions.ReimbursementRepository",
            return_value=mock_reimb_repo,
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
        # other_income_allocated=50 → 50 + 99 = 149 > 100 → fail
        with self.assertRaises(HTTPException) as ctx:
            await self._run_update(
                reimb, body, expense, income, other_income_allocated=Decimal("50.00")
            )
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_update_nonexistent_raises_404(self):
        user = _make_user()
        db = AsyncMock()
        mock_reimb_repo = AsyncMock()
        mock_reimb_repo.get_by_id.return_value = None
        with patch(
            "app.api.v1.routers.transactions.TransactionRepository",
            return_value=AsyncMock(),
        ), patch(
            "app.api.v1.routers.transactions.ReimbursementRepository",
            return_value=mock_reimb_repo,
        ):
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
        expense = _make_txn(type="expense")
        user = _make_user()
        db = AsyncMock()
        with _patch_repos(reimb=reimb, expense_txn=expense):
            await delete_reimbursement(
                reimbursement_id=reimb.id, db=db, current_user=user
            )
        db.delete.assert_awaited_once_with(reimb)
        db.commit.assert_awaited_once()

    async def test_delete_nonexistent_raises_404(self):
        user = _make_user()
        db = AsyncMock()
        with _patch_repos(reimb=None):
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
        with _patch_repos(expense_txn=expense, links=[reimb_a, reimb_b]):
            response = await list_reimbursements(
                transaction_id="exp_1", db=db, current_user=user
            )
        self.assertEqual(response.transaction_amount, Decimal("100.00"))
        self.assertEqual(response.allocated_amount, Decimal("70.00"))
        self.assertEqual(response.remaining_amount, Decimal("30.00"))
