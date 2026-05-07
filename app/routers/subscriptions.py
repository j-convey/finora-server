from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.subscription import SubscriptionStatus, RecurrenceUnit
from app.models.user import User
from app.services.subscription import SubscriptionFilters, SubscriptionService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SubscriptionResponse(BaseModel):
    id: str
    household_id: int
    name: str
    merchant_name: Optional[str] = None
    category: Optional[str] = None
    expected_amount: Optional[float] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    recurrence_interval: int
    recurrence_unit: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    next_due_date: Optional[date] = None
    status: str
    auto_link_enabled: bool
    matching_notes: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    name: str
    merchant_name: Optional[str] = None
    category: Optional[str] = None
    expected_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    recurrence_interval: int = 1
    recurrence_unit: str = RecurrenceUnit.MONTH
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    next_due_date: Optional[date] = None
    status: str = SubscriptionStatus.ACTIVE
    auto_link_enabled: bool = True
    matching_notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    merchant_name: Optional[str] = None
    category: Optional[str] = None
    expected_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    recurrence_interval: Optional[int] = None
    recurrence_unit: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    next_due_date: Optional[date] = None
    status: Optional[str] = None
    auto_link_enabled: Optional[bool] = None
    matching_notes: Optional[str] = None

    model_config = {"extra": "ignore"}


def _to_response(sub) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        household_id=sub.household_id,
        name=sub.name,
        merchant_name=sub.merchant_name,
        category=sub.category,
        expected_amount=float(sub.expected_amount) if sub.expected_amount is not None else None,
        min_amount=float(sub.min_amount) if sub.min_amount is not None else None,
        max_amount=float(sub.max_amount) if sub.max_amount is not None else None,
        recurrence_interval=sub.recurrence_interval,
        recurrence_unit=sub.recurrence_unit,
        start_date=sub.start_date,
        end_date=sub.end_date,
        next_due_date=sub.next_due_date,
        status=sub.status,
        auto_link_enabled=sub.auto_link_enabled,
        matching_notes=sub.matching_notes,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    status: Optional[str] = Query(None, description="Filter by status: active, paused, canceled"),
    upcoming: bool = Query(False, description="Return only active subscriptions with a next_due_date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = SubscriptionFilters(
        status=SubscriptionStatus(status) if status else None,
        upcoming_only=upcoming,
    )
    service = SubscriptionService(db)
    subs = await service.find_all_for_user(household_id=current_user.household_id, filters=filters)
    return [_to_response(s) for s in subs]


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    data = body.model_dump(exclude_unset=False)
    sub = await service.create_subscription(household_id=current_user.household_id, data=data)
    await db.commit()
    return _to_response(sub)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.find_by_id(subscription_id, current_user.household_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _to_response(sub)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: str,
    body: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.update_subscription(
        subscription_id=subscription_id,
        household_id=current_user.household_id,
        data=body.model_dump(exclude_unset=True),
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await db.commit()
    return _to_response(sub)


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    hard: bool = Query(False, description="Permanently delete (default: soft-cancel)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    ok = await service.delete_subscription(
        subscription_id=subscription_id,
        household_id=current_user.household_id,
        soft_delete=not hard,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await db.commit()
    return {"ok": True}


@router.post("/subscriptions/{subscription_id}/link/{transaction_id}")
async def link_transaction(
    subscription_id: str,
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    tx = await service.link_transaction(
        transaction_id=transaction_id,
        subscription_id=subscription_id,
        household_id=current_user.household_id,
    )
    if tx is None:
        raise HTTPException(status_code=404, detail="Subscription or transaction not found")
    await db.commit()
    return {"ok": True, "transaction_id": tx.id, "subscription_id": tx.subscription_id}


@router.delete("/subscriptions/{subscription_id}/link/{transaction_id}")
async def unlink_transaction(
    subscription_id: str,
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    tx = await service.unlink_transaction(transaction_id=transaction_id, household_id=current_user.household_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.commit()
    return {"ok": True, "transaction_id": tx.id, "subscription_id": None}
