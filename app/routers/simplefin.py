from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.account import Account as AccountModel
from app.models.simplefin_config import SimplefinConfig
from app.models.transaction import Transaction as TransactionModel
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


def _pick_color(index: int) -> str:
    return _COLORS[index % len(_COLORS)]


async def _do_fetch(access_url: str, db: AsyncSession) -> dict:
    """Pull data from SimpleFIN, upsert accounts + transactions, return summary."""
    data = await fetch_simplefin_data(access_url)
    sf_accounts = data.get("accounts", [])

    institutions: List[str] = []
    accounts_updated = 0
    transactions_added = 0
    new_transactions: List[NewTransaction] = []

    # Build account name lookup
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

            txn_id = sf_txn["id"]
            is_new = (await db.get(TransactionModel, txn_id)) is None

            await db.merge(TransactionModel(
                id=txn_id,
                title=raw_description,
                original_description=raw_description,
                merchant_name=sf_txn.get("payee") or sf_txn.get("merchant_name"),
                provider_transaction_id=txn_id,
                amount=abs(amount_raw),
                type=txn_type,
                category=None,
                provider_category=provider_category,
                date=datetime.fromtimestamp(sf_txn["posted"], tz=timezone.utc),
                pending=sf_txn.get("pending", False),
                account_id=account_id,
                subscription_id=None,
                notes=None,
            ))

            if is_new:
                transactions_added += 1
                if txn_type == "expense":
                    new_transactions.append(NewTransaction(
                        id=txn_id,
                        title=raw_description,
                        amount=abs(amount_raw),
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
async def get_status(db: AsyncSession = Depends(get_db)):
    config = await db.get(SimplefinConfig, 1)
    if not config:
        return SimplefinStatusResponse(connected=False)
    return SimplefinStatusResponse(
        connected=True,
        institutions=config.institutions,
        last_synced_at=config.last_synced_at,
    )


@router.post("/connect", response_model=SimplefinStatusResponse)
async def connect(body: SimplefinConnectRequest, db: AsyncSession = Depends(get_db)):
    try:
        access_url = await claim_access_url(body.setup_token)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    encrypted = encrypt(access_url, settings.SECRET_KEY)
    result = await _do_fetch(access_url, db)

    await db.merge(SimplefinConfig(
        id=1,
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
async def fetch(db: AsyncSession = Depends(get_db)):
    config = await db.get(SimplefinConfig, 1)
    if not config:
        raise HTTPException(status_code=400, detail="SimpleFIN is not connected")

    encrypted_url = config.access_url_encrypted
    access_url = decrypt(encrypted_url, settings.SECRET_KEY)
    result = await _do_fetch(access_url, db)

    # Update config sync metadata
    await db.merge(SimplefinConfig(
        id=1,
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
async def disconnect(db: AsyncSession = Depends(get_db)):
    config = await db.get(SimplefinConfig, 1)
    if config:
        await db.delete(config)
        await db.commit()
    return {"ok": True}
