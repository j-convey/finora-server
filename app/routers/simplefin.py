from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.account import Account as AccountModel
from app.models.category import Category as CategoryModel
from app.models.simplefin_config import SimplefinConfig
from app.models.transaction import Transaction as TransactionModel
from app.models.user import User
from app.schemas.simplefin import (
    SimplefinConnectRequest,
    SimplefinFetchResponse,
    SimplefinStatusResponse,
    NewTransaction,
)
from app.services.simplefin import claim_access_url, fetch_simplefin_data

router = APIRouter()

_COLORS = [
    "#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
    "#009688", "#F44336", "#00BCD4", "#FF5722",
]

# Maps SimpleFIN provider category strings (lowercased) to our system category names.
# provider_category is preserved as-is; this mapping only determines category_id.
_PROVIDER_CATEGORY_MAP: dict[str, str] = {
    "food and drink": "Restaurants & Bars",
    "food & drink": "Restaurants & Bars",
    "restaurants": "Restaurants & Bars",
    "dining": "Restaurants & Bars",
    "fast food": "Restaurants & Bars",
    "coffee shops": "Coffee Shops",
    "groceries": "Groceries",
    "supermarkets": "Groceries",
    "shopping": "Shopping",
    "general merchandise": "Shopping",
    "clothing": "Clothing",
    "electronics": "Electronics",
    "travel": "Travel & Vacation",
    "airlines": "Travel & Vacation",
    "hotels": "Travel & Vacation",
    "entertainment": "Entertainment & Recreation",
    "recreation": "Entertainment & Recreation",
    "subscription": "Entertainment & Recreation",
    "streaming": "Entertainment & Recreation",
    "utilities": "Gas & Electric",
    "gas and electric": "Gas & Electric",
    "electric": "Gas & Electric",
    "internet": "Internet & Cable",
    "cable": "Internet & Cable",
    "phone": "Phone",
    "mobile phone": "Phone",
    "income": "Paychecks",
    "payroll": "Paychecks",
    "direct deposit": "Paychecks",
    "transfer": "Transfer",
    "gas": "Gas",
    "automotive": "Gas",
    "auto": "Auto Payment",
    "insurance": "Insurance",
    "health": "Medical",
    "healthcare": "Medical",
    "medical": "Medical",
    "pharmacy": "Medical",
    "fitness": "Fitness",
    "gym": "Fitness",
    "education": "Education",
    "taxes": "Taxes",
    "personal care": "Personal",
    "pets": "Pets",
    "mortgage": "Mortgage",
    "rent": "Rent",
    "home improvement": "Home Improvement",
    "atm": "Cash & ATM",
    "cash": "Cash & ATM",
    "fees": "Financial Fees",
    "bank fees": "Financial Fees",
    "interest": "Interest",
    "credit card payment": "Credit Card Payment",
}


def _pick_color(index: int) -> str:
    return _COLORS[index % len(_COLORS)]


async def _load_category_map(db: AsyncSession) -> tuple[dict[str, int], int]:
    """Load all system categories into a name→id dict and return the Uncategorized ID."""
    result = await db.execute(
        select(CategoryModel.id, CategoryModel.name).where(
            CategoryModel.household_id.is_(None)
        )
    )
    name_to_id = {name.lower(): cat_id for cat_id, name in result.all()}
    uncategorized_id = name_to_id.get("uncategorized", next(iter(name_to_id.values())))
    return name_to_id, uncategorized_id


def _map_provider_category(
    provider_category: str | None,
    name_to_id: dict[str, int],
    uncategorized_id: int,
) -> int:
    """Map a SimpleFIN provider category string to a system category_id.

    Strategy:
    1. Direct case-insensitive match against system category names.
    2. Lookup in our provider→system mapping table.
    3. Fall back to Uncategorized.
    """
    if not provider_category:
        return uncategorized_id

    lower = provider_category.strip().lower()

    # Direct match against system category names
    if lower in name_to_id:
        return name_to_id[lower]

    # Mapped match via provider dictionary
    mapped = _PROVIDER_CATEGORY_MAP.get(lower)
    if mapped and mapped.lower() in name_to_id:
        return name_to_id[mapped.lower()]

    return uncategorized_id


async def _do_fetch(access_url: str, db: AsyncSession) -> dict:
    """Pull data from SimpleFIN, upsert accounts + transactions, return summary."""
    data = await fetch_simplefin_data(access_url)
    sf_accounts = data.get("accounts", [])

    # Load category lookup once for the entire sync
    name_to_id, uncategorized_id = await _load_category_map(db)

    institutions: List[str] = []
    accounts_updated = 0
    transactions_added = 0
    new_transactions: List[NewTransaction] = []

    account_names: dict[str, str] = {}

    for idx, sf_acct in enumerate(sf_accounts):
        org_name = sf_acct.get("org", {}).get("name")
        if org_name and org_name not in institutions:
            institutions.append(org_name)

        account_id = sf_acct["id"]
        account_name = sf_acct.get("name", "Unknown")
        account_names[account_id] = account_name
        balance = Decimal(sf_acct.get("balance", "0"))

        # Preserve color and type if the account already exists
        existing = await db.get(AccountModel, account_id)
        color = existing.color if existing else _pick_color(idx)
        acct_type = existing.type if existing else "checking"

        await db.merge(AccountModel(
            id=account_id,
            household_id=1,
            name=account_name,
            type=acct_type,
            balance=balance,
            available_balance=Decimal(str(sf_acct["balance-available"])) if sf_acct.get("balance-available") else None,
            institution_name=org_name,
            color=color,
        ))
        accounts_updated += 1

        for sf_txn in sf_acct.get("transactions", []):
            amount_raw = Decimal(sf_txn.get("amount", "0"))
            txn_type = "income" if amount_raw >= 0 else "expense"
            raw_description = sf_txn.get("description", "Unknown")
            extra = sf_txn.get("extra") or {}
            provider_category = (
                sf_txn.get("category")
                or extra.get("category")
                or extra.get("simplefin_category")
            )

            # Map provider category string → category_id (preserving raw in provider_category)
            category_id = _map_provider_category(provider_category, name_to_id, uncategorized_id)

            txn_id = sf_txn["id"]
            incoming_amount = abs(amount_raw)
            existing_txn = await db.get(TransactionModel, txn_id)
            is_new = existing_txn is None

            # Split-parent amount-drift check (pending → posted edge case).
            # If SimpleFIN changes the amount of a transaction that the user already
            # split, the split math is now invalid.  We update the parent amount and
            # flag it for user review so the client can prompt a re-reconcile.
            if (
                existing_txn is not None
                and existing_txn.is_split_parent
                and existing_txn.amount != incoming_amount
            ):
                existing_txn.amount = incoming_amount
                existing_txn.requires_user_review = True
                existing_txn.pending = sf_txn.get("pending", False)
                db.add(existing_txn)
                # Skip the full merge below — we've handled this row already.
                continue

            await db.merge(TransactionModel(
                id=txn_id,
                title=raw_description,
                original_description=raw_description,
                merchant_name=sf_txn.get("payee") or sf_txn.get("merchant_name"),
                provider_transaction_id=txn_id,
                amount=incoming_amount,
                type=txn_type,
                category_id=category_id,
                provider_category=provider_category,
                date=datetime.fromtimestamp(sf_txn["posted"], tz=timezone.utc),
                pending=sf_txn.get("pending", False),
                account_id=account_id,
                subscription_id=None,
                notes=None,
                is_split_parent=False,
                parent_transaction_id=None,
                requires_user_review=False,
            ))

            if is_new:
                transactions_added += 1
                if txn_type == "expense":
                    new_transactions.append(NewTransaction(
                        id=txn_id,
                        title=raw_description,
                        amount=incoming_amount,
                        account_name=account_names.get(account_id),
                    ))

    await db.commit()

    return {
        "accounts_updated": accounts_updated,
        "transactions_added": transactions_added,
        "new_transactions": new_transactions,
        "institutions": institutions,
        "last_synced_at": datetime.now(tz=timezone.utc),
    }


@router.get("/status", response_model=SimplefinStatusResponse)
async def get_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = await db.get(SimplefinConfig, 1)
    if not config:
        return SimplefinStatusResponse(connected=False)
    return SimplefinStatusResponse(
        connected=True,
        institutions=config.institutions,
        last_synced_at=config.last_synced_at,
    )


@router.post("/connect", response_model=SimplefinStatusResponse)
async def connect(
    body: SimplefinConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        access_url = await claim_access_url(body.setup_token)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    encrypted = encrypt(access_url, settings.SECRET_KEY)
    result = await _do_fetch(access_url, db)

    await db.merge(SimplefinConfig(
        household_id=1,
        access_url_encrypted=encrypted,
        institutions=result["institutions"],
        last_synced_at=result["last_synced_at"],
    ))
    await db.commit()

    return SimplefinStatusResponse(
        connected=True,
        institutions=result["institutions"],
        last_synced_at=result["last_synced_at"],
    )


@router.post("/fetch", response_model=SimplefinFetchResponse)
async def fetch(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = await db.get(SimplefinConfig, 1)
    if not config:
        raise HTTPException(status_code=400, detail="SimpleFIN is not connected")

    encrypted_url = config.access_url_encrypted
    access_url = decrypt(encrypted_url, settings.SECRET_KEY)
    result = await _do_fetch(access_url, db)

    # Update config sync metadata
    await db.merge(SimplefinConfig(
        household_id=1,
        access_url_encrypted=encrypted_url,
        institutions=result["institutions"],
        last_synced_at=result["last_synced_at"],
    ))
    await db.commit()

    return SimplefinFetchResponse(
        ok=True,
        accounts_updated=result["accounts_updated"],
        transactions_added=result["transactions_added"],
        new_transactions=result["new_transactions"],
    )


@router.delete("/disconnect")
async def disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = await db.get(SimplefinConfig, 1)
    if config:
        await db.delete(config)
        await db.commit()
    return {"ok": True}
