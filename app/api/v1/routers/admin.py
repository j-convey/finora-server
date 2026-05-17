from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from pydantic import BaseModel

from app.core.auth import get_current_user, get_admin_user
from app.core.database import get_db
from app.infrastructure.models.account import Account as AccountModel
from app.infrastructure.models.transaction import Transaction as TransactionModel
from app.infrastructure.models.user import User
from app.infrastructure.models.budget import Budget as BudgetModel
from app.infrastructure.models.account_snapshot import (
    AccountSnapshot as AccountSnapshotModel,
)
from app.infrastructure.models.simplefin_config import (
    SimplefinConfig as SimplefinConfigModel,
)
from app.infrastructure.models.subscription import (
    RecurrenceUnit,
    Subscription as SubscriptionModel,
)
from app.infrastructure.models.transaction import Transaction
from app.application.subscription import SubscriptionService

router = APIRouter()


# ============================================================================
# Export/Import Models
# ============================================================================


class DatabaseExport(BaseModel):
    """Complete database state export."""

    version: str = "1.0"
    exported_at: str
    accounts: List[Dict[str, Any]]
    subscriptions: List[Dict[str, Any]]
    transactions: List[Dict[str, Any]]
    budgets: List[Dict[str, Any]]
    account_snapshots: List[Dict[str, Any]]
    simplefin_config: Dict[str, Any] | None = None


class DatabaseImport(BaseModel):
    """Database import payload — accepts exported data to restore."""

    accounts: List[Dict[str, Any]]
    subscriptions: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]]
    budgets: List[Dict[str, Any]]
    account_snapshots: List[Dict[str, Any]]
    simplefin_config: Dict[str, Any] | None = None


def _serialize_value(val: Any) -> Any:
    """Convert database values to JSON-serializable types."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        return val.isoformat()
    return val


async def _export_row_dicts(db: AsyncSession, model_cls, order_by=None) -> List[Dict]:
    """Generic export: fetch all rows from a table and return as dicts."""
    if order_by is not None:
        stmt = select(model_cls).order_by(order_by)
    else:
        stmt = select(model_cls)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            col: _serialize_value(getattr(row, col))
            for col in row.__table__.columns.keys()
        }
        for row in rows
    ]


@router.post("/admin/reset-database")
async def reset_database(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """
    **CAUTION: This endpoint deletes ALL data from the database.**

    **Requires admin role.**

    Clears all records from the following tables:
    - account_snapshots
    - transactions
    - subscriptions
    - accounts
    - budgets
    - categories
    - simplefin_config

    This is useful for resetting to a clean state during development/testing.

    **Response:**
    - `200 OK` with summary of deleted records

    **Example usage:**
    ```bash
    curl -X POST http://localhost:8000/api/admin/reset-database
    ```

    This is an intentionally destructive operation with no undo.
    """
    try:
        # Delete in dependency order (dependent tables first)
        tables_deleted = {}

        # 1. account_snapshots (household-scoped, no FK issue with raw DELETE)
        result = await db.execute(text("DELETE FROM account_snapshots"))
        tables_deleted["account_snapshots"] = result.rowcount

        # 2. transactions (depends on account_id)
        result = await db.execute(text("DELETE FROM transactions"))
        tables_deleted["transactions"] = result.rowcount

        # 3. subscriptions (referenced by transactions via SET NULL FK)
        result = await db.execute(text("DELETE FROM subscriptions"))
        tables_deleted["subscriptions"] = result.rowcount

        # 4. accounts (independent)
        result = await db.execute(text("DELETE FROM accounts"))
        tables_deleted["accounts"] = result.rowcount

        # 5. budgets (independent)
        result = await db.execute(text("DELETE FROM budgets"))
        tables_deleted["budgets"] = result.rowcount

        # 6. categories (independent)
        result = await db.execute(text("DELETE FROM categories"))
        tables_deleted["categories"] = result.rowcount

        # 7. simplefin_config (independent)
        result = await db.execute(text("DELETE FROM simplefin_config"))
        tables_deleted["simplefin_config"] = result.rowcount

        await db.commit()

        return {
            "ok": True,
            "message": "Database reset complete. All data deleted.",
            "deleted_records": tables_deleted,
        }

    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset database: {str(exc)}",
        )


@router.get("/admin/export-database", response_model=DatabaseExport)
async def export_database(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """
    Export the entire database as JSON.

    Returns all accounts, transactions, budgets, snapshots, and SimpleFIN config
    in a single JSON object that can be saved as a backup or transferred between
    instances.

    **Response:**
    ```json
    {
      "version": "1.0",
      "exported_at": "2026-05-06T12:34:56+00:00",
      "accounts": [...],
      "transactions": [...],
      "budgets": [...],
      "account_snapshots": [...],
      "simplefin_config": {...}
    }
    ```

    **Usage:**
    ```bash
    curl http://localhost:8000/api/admin/export-database > backup.json
    ```
    """
    try:
        # Export all tables
        accounts = await _export_row_dicts(db, AccountModel, AccountModel.name)
        subscriptions = await _export_row_dicts(
            db, SubscriptionModel, SubscriptionModel.name
        )
        transactions = await _export_row_dicts(
            db, TransactionModel, TransactionModel.date.desc()
        )
        budgets = await _export_row_dicts(db, BudgetModel, BudgetModel.category)
        snapshots = await _export_row_dicts(
            db, AccountSnapshotModel, AccountSnapshotModel.snapshot_date
        )

        # SimpleFIN config is optional (at most 1 row)
        result = await db.execute(select(SimplefinConfigModel))
        config_row = result.scalar_one_or_none()
        simplefin_config = (
            {
                col: _serialize_value(getattr(config_row, col))
                for col in config_row.__table__.columns.keys()
            }
            if config_row
            else None
        )

        return DatabaseExport(
            version="1.0",
            exported_at=datetime.now(tz=timezone.utc).isoformat(),
            accounts=accounts,
            subscriptions=subscriptions,
            transactions=transactions,
            budgets=budgets,
            account_snapshots=snapshots,
            simplefin_config=simplefin_config,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(exc)}")


@router.post("/admin/import-database")
async def import_database(
    payload: DatabaseImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """
    Import a previously exported database state.
    
    **Requires admin role.**

    **CAUTION:** This will:
    1. Delete all existing data
    2. Restore from the provided JSON backup

    Use this to restore a backup or synchronize data between instances.

    **Request body:** A `DatabaseExport` object (or its subset)

    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/admin/import-database \\
      -H "Content-Type: application/json" \\
      -d @backup.json
    ```

    **Response:**
    ```json
    {
      "ok": true,
      "message": "Database import complete.",
      "imported_records": {
        "accounts": 5,
        "transactions": 42,
        "budgets": 7,
        "account_snapshots": 31,
        "simplefin_config": 0
      }
    }
    ```
    """
    try:
        imported = {}

        # 1. Clear existing data (same order as reset-database)
        await db.execute(text("DELETE FROM account_snapshots"))
        await db.execute(text("DELETE FROM transactions"))
        await db.execute(text("DELETE FROM subscriptions"))
        await db.execute(text("DELETE FROM accounts"))
        await db.execute(text("DELETE FROM budgets"))
        await db.execute(text("DELETE FROM simplefin_config"))

        # 2. Insert accounts first (transactions depend on account_id)
        for account_data in payload.accounts:
            account = AccountModel(**account_data)
            db.add(account)
        imported["accounts"] = len(payload.accounts)

        # 3. Insert subscriptions
        for sub_data in payload.subscriptions:
            sub = SubscriptionModel(**sub_data)
            db.add(sub)
        imported["subscriptions"] = len(payload.subscriptions)

        # 4. Insert transactions
        for txn_data in payload.transactions:
            txn = TransactionModel(**txn_data)
            db.add(txn)
        imported["transactions"] = len(payload.transactions)

        # 5. Insert budgets
        for budget_data in payload.budgets:
            budget = BudgetModel(**budget_data)
            db.add(budget)
        imported["budgets"] = len(payload.budgets)

        # 6. Insert account snapshots
        for snapshot_data in payload.account_snapshots:
            snapshot = AccountSnapshotModel(**snapshot_data)
            db.add(snapshot)
        imported["account_snapshots"] = len(payload.account_snapshots)

        # 7. Insert SimpleFIN config (if provided)
        if payload.simplefin_config:
            config = SimplefinConfigModel(**payload.simplefin_config)
            db.add(config)
            imported["simplefin_config"] = 1
        else:
            imported["simplefin_config"] = 0

        await db.commit()

        return {
            "ok": True,
            "message": "Database import complete.",
            "imported_records": imported,
        }

    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {str(exc)}",
        )


@router.get("/admin/subscriptions/suggestions")
async def subscription_suggestions(
    current_user: User = Depends(get_current_user),
    min_occurrences: int = Query(3, ge=2, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Suggest likely subscriptions from existing transactions.

    This endpoint does not modify data; it helps operators backfill by
    inspecting repeated charges grouped by merchant/title.
    """
    service = SubscriptionService(db)
    suggestions = await service.suggest_from_transactions(
        household_id=current_user.household_id,
        min_occurrences=min_occurrences,
    )
    return {
        "ok": True,
        "count": len(suggestions),
        "suggestions": suggestions,
    }


@router.post("/admin/subscriptions/backfill")
async def backfill_subscriptions(
    current_user: User = Depends(get_current_user),
    min_occurrences: int = Query(3, ge=2, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Create subscriptions from repeated transactions and link history.

    This is an operator-oriented endpoint to bootstrap subscription data from
    legacy transactions. It intentionally keeps matching simple and conservative.
    """
    service = SubscriptionService(db)
    suggestions = await service.suggest_from_transactions(
        household_id=current_user.household_id,
        min_occurrences=min_occurrences,
    )

    created = 0
    linked = 0

    for item in suggestions:
        sub = await service.create_subscription(
            household_id=current_user.household_id,
            data={
                "name": item["name"],
                "merchant_name": item["merchant_name"],
                "min_amount": item["min_amount"],
                "max_amount": item["max_amount"],
                "recurrence_interval": 1,
                "recurrence_unit": RecurrenceUnit.MONTH,
            },
        )
        created += 1

        result = await db.execute(
            select(Transaction).where(
                Transaction.subscription_id.is_(None),
                Transaction.type == "expense",
                func.lower(func.coalesce(Transaction.merchant_name, Transaction.title))
                == item["merchant_name"].lower(),
            )
        )
        txs = result.scalars().all()
        for tx in txs:
            tx.subscription_id = sub.id
            linked += 1

    await db.commit()
    return {
        "ok": True,
        "created_subscriptions": created,
        "linked_transactions": linked,
    }
