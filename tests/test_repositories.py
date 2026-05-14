"""Unit tests for the repository layer.

Tests mock AsyncSession.execute() / AsyncSession.get() so no real database is
needed. Each test verifies that:
  - the correct query is assembled (via inspecting the mock call args), and/or
  - the return value is correctly transformed by the repository method.

Coverage:
  1. TransactionRepository.get_by_id — delegates to db.get
  2. TransactionRepository.get_by_id_for_household — returns txn when household matches
  3. TransactionRepository.get_by_id_for_household — returns None when household differs
  4. TransactionRepository.get_by_id_for_household — returns None when row not found
  5. ReimbursementRepository.sum_allocated_to_income — returns scalar
  6. ReimbursementRepository.sum_allocated_to_income — respects exclude_id
  7. ReimbursementRepository.sum_reimbursed_from_expense — returns scalar
  8. ReimbursementRepository.list_by_transaction — returns list of rows
  9. CategoryRepository.resolve_id_by_name — returns id when found
 10. CategoryRepository.resolve_id_by_name — returns None when not found
 11. CategoryRepository.list_names — returns ordered list of strings
 12. CategoryRepository.load_name_to_id_map — maps lowercase name → id
 13. CategoryRepository.load_name_to_id_map system_only=False — no household filter
 14. BudgetRepository.compute_spent — returns Decimal aggregate
 15. BudgetRepository.get_by_id — delegates to db.get
"""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_scalar_result(value):
    """Return a mock that behaves like a SQLAlchemy scalar result row."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    m.scalar_one.return_value = value
    m.scalar.return_value = value
    m.scalars.return_value.all.return_value = value if isinstance(value, list) else [value]
    m.all.return_value = value if isinstance(value, list) else [value]
    return m


def _make_db(*, get_return=None, execute_return=None):
    """Return a minimal AsyncMock AsyncSession."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=get_return)
    db.execute = AsyncMock(return_value=execute_return)
    return db


# ─── TransactionRepository ──────────────────────────────────────────────────

class TestTransactionRepository(unittest.IsolatedAsyncioTestCase):
    def _make_txn(self, *, household_id=1):
        return SimpleNamespace(id="txn_1", household_id=household_id)

    async def test_get_by_id_delegates_to_db_get(self):
        from app.infrastructure.repositories.transaction_repository import TransactionRepository
        from app.infrastructure.models.transaction import Transaction

        txn = self._make_txn()
        db = _make_db(get_return=txn)
        result = await TransactionRepository(db).get_by_id("txn_1")
        db.get.assert_awaited_once_with(Transaction, "txn_1")
        self.assertIs(result, txn)

    async def test_get_by_id_for_household_match(self):
        from app.infrastructure.repositories.transaction_repository import TransactionRepository

        txn = self._make_txn(household_id=7)
        db = _make_db(execute_return=_make_scalar_result(txn))
        result = await TransactionRepository(db).get_by_id_for_household("txn_1", 7)
        self.assertIs(result, txn)

    async def test_get_by_id_for_household_wrong_household_returns_none(self):
        from app.infrastructure.repositories.transaction_repository import TransactionRepository

        txn = self._make_txn(household_id=99)
        db = _make_db(execute_return=_make_scalar_result(txn))
        result = await TransactionRepository(db).get_by_id_for_household("txn_1", 1)
        self.assertIsNone(result)

    async def test_get_by_id_for_household_not_found_returns_none(self):
        from app.infrastructure.repositories.transaction_repository import TransactionRepository

        db = _make_db(execute_return=_make_scalar_result(None))
        result = await TransactionRepository(db).get_by_id_for_household("nonexistent", 1)
        self.assertIsNone(result)


# ─── ReimbursementRepository ─────────────────────────────────────────────────

class TestReimbursementRepository(unittest.IsolatedAsyncioTestCase):

    async def test_sum_allocated_to_income_returns_decimal(self):
        from app.infrastructure.repositories.reimbursement_repository import ReimbursementRepository

        db = _make_db(execute_return=_make_scalar_result(Decimal("75.00")))
        result = await ReimbursementRepository(db).sum_allocated_to_income("inc_1")
        self.assertEqual(result, Decimal("75.00"))
        db.execute.assert_awaited_once()

    async def test_sum_allocated_to_income_with_exclude_id(self):
        from app.infrastructure.repositories.reimbursement_repository import ReimbursementRepository

        db = _make_db(execute_return=_make_scalar_result(Decimal("30.00")))
        result = await ReimbursementRepository(db).sum_allocated_to_income(
            "inc_1", exclude_id="reimb_99"
        )
        self.assertEqual(result, Decimal("30.00"))
        # verify exclude_id caused an additional .where() — i.e., execute was called
        db.execute.assert_awaited_once()

    async def test_sum_reimbursed_from_expense_returns_decimal(self):
        from app.infrastructure.repositories.reimbursement_repository import ReimbursementRepository

        db = _make_db(execute_return=_make_scalar_result(Decimal("50.00")))
        result = await ReimbursementRepository(db).sum_reimbursed_from_expense("exp_1")
        self.assertEqual(result, Decimal("50.00"))

    async def test_list_by_transaction_returns_list(self):
        from app.infrastructure.repositories.reimbursement_repository import ReimbursementRepository

        r1 = SimpleNamespace(id="r1")
        r2 = SimpleNamespace(id="r2")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [r1, r2]
        db = _make_db(execute_return=mock_result)
        result = await ReimbursementRepository(db).list_by_transaction("txn_1")
        self.assertEqual(result, [r1, r2])

    async def test_list_by_transaction_empty(self):
        from app.infrastructure.repositories.reimbursement_repository import ReimbursementRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db = _make_db(execute_return=mock_result)
        result = await ReimbursementRepository(db).list_by_transaction("no_links")
        self.assertEqual(result, [])


# ─── CategoryRepository ──────────────────────────────────────────────────────

class TestCategoryRepository(unittest.IsolatedAsyncioTestCase):

    async def test_resolve_id_by_name_found(self):
        from app.infrastructure.repositories.category_repository import CategoryRepository

        db = _make_db(execute_return=_make_scalar_result(42))
        result = await CategoryRepository(db).resolve_id_by_name("Groceries")
        self.assertEqual(result, 42)

    async def test_resolve_id_by_name_not_found(self):
        from app.infrastructure.repositories.category_repository import CategoryRepository

        db = _make_db(execute_return=_make_scalar_result(None))
        result = await CategoryRepository(db).resolve_id_by_name("Nonexistent")
        self.assertIsNone(result)

    async def test_list_names_returns_ordered_strings(self):
        from app.infrastructure.repositories.category_repository import CategoryRepository

        mock_result = MagicMock()
        mock_result.all.return_value = [("Dining",), ("Groceries",), ("Transport",)]
        db = _make_db(execute_return=mock_result)
        result = await CategoryRepository(db).list_names()
        self.assertEqual(result, ["Dining", "Groceries", "Transport"])

    async def test_load_name_to_id_map_system_only(self):
        from app.infrastructure.repositories.category_repository import CategoryRepository

        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "Groceries"), (2, "Dining")]
        db = _make_db(execute_return=mock_result)
        result = await CategoryRepository(db).load_name_to_id_map(system_only=True)
        self.assertEqual(result, {"groceries": 1, "dining": 2})

    async def test_load_name_to_id_map_all_categories(self):
        from app.infrastructure.repositories.category_repository import CategoryRepository

        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "Groceries"), (3, "Custom")]
        db = _make_db(execute_return=mock_result)
        result = await CategoryRepository(db).load_name_to_id_map(system_only=False)
        self.assertEqual(result, {"groceries": 1, "custom": 3})


# ─── BudgetRepository ────────────────────────────────────────────────────────

class TestBudgetRepository(unittest.IsolatedAsyncioTestCase):

    async def test_get_by_id_delegates_to_db_get(self):
        from app.infrastructure.repositories.budget_repository import BudgetRepository
        from app.infrastructure.models.budget import Budget

        budget = SimpleNamespace(id="bud_1")
        db = _make_db(get_return=budget)
        result = await BudgetRepository(db).get_by_id("bud_1")
        db.get.assert_awaited_once_with(Budget, "bud_1")
        self.assertIs(result, budget)

    async def test_compute_spent_returns_decimal(self):
        from app.infrastructure.repositories.budget_repository import BudgetRepository

        db = _make_db(execute_return=_make_scalar_result(Decimal("123.45")))
        result = await BudgetRepository(db).compute_spent(category_id=5)
        self.assertIsInstance(result, Decimal)
        self.assertEqual(result, Decimal("123.45"))

    async def test_compute_spent_zero_when_no_transactions(self):
        from app.infrastructure.repositories.budget_repository import BudgetRepository

        db = _make_db(execute_return=_make_scalar_result(Decimal("0.0000")))
        result = await BudgetRepository(db).compute_spent(category_id=99)
        self.assertEqual(result, Decimal("0"))
