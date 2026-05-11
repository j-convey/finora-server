"""Transfer detection service.

During a SimpleFIN sync, all accounts and their transactions are available in
memory simultaneously. This module identifies internal transfer pairs —
transactions that represent money moving between the user's own accounts — so
they are not miscounted as income or expense.

Algorithm (two-pass):
  The caller (Pass 1) collects RawTransaction objects across all accounts.
  detect_transfers() (Pass 2) matches positive/negative pairs across *different*
  accounts with equal absolute amounts and dates within TRANSFER_WINDOW_DAYS.
  The matched transaction IDs are returned so the caller can tag them
  type="transfer" before writing to the database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

# Maximum number of calendar days allowed between the two legs of a transfer.
# ACH transfers typically post within 1–2 days; 3 gives a safe buffer.
TRANSFER_WINDOW_DAYS = 3


@dataclass(frozen=True)
class RawTransaction:
    """Minimal snapshot of a SimpleFIN transaction used for transfer matching."""

    id: str
    account_id: str
    # Original signed value from SimpleFIN (positive = credit, negative = debit).
    signed_amount: Decimal
    date: datetime


def detect_transfers(transactions: list[RawTransaction]) -> set[str]:
    """Return the set of transaction IDs that form matched internal transfer pairs.

    Matching criteria — all must hold:
    - One leg is a credit (positive), the other is a debit (negative).
    - Absolute amounts are exactly equal.
    - They belong to *different* accounts (same-account entries are never transfers).
    - Their dates are within TRANSFER_WINDOW_DAYS of each other.

    Matching is greedy and one-to-one: each transaction ID is consumed at most
    once, and the closest-in-time counterpart is always preferred to minimise
    false positives on duplicate amounts (e.g. recurring payments).
    """
    window = timedelta(days=TRANSFER_WINDOW_DAYS)

    positives = [t for t in transactions if t.signed_amount > 0]
    negatives = [t for t in transactions if t.signed_amount < 0]

    # Index: absolute_amount → list of debit (negative) transactions.
    neg_by_amount: dict[Decimal, list[RawTransaction]] = {}
    for txn in negatives:
        neg_by_amount.setdefault(abs(txn.signed_amount), []).append(txn)

    transfer_ids: set[str] = set()
    used: set[str] = set()

    # Process credits in chronological order so that when two credits share the
    # same amount, the earliest one gets the closest debit — consistent with how
    # banks post transfers.
    for pos in sorted(positives, key=lambda t: t.date):
        if pos.id in used:
            continue

        candidates = neg_by_amount.get(pos.signed_amount, [])
        best: RawTransaction | None = None
        best_delta = timedelta.max

        for neg in candidates:
            if neg.id in used:
                continue
            if neg.account_id == pos.account_id:
                # Same account — not an internal transfer.
                continue

            delta = abs(pos.date - neg.date)
            if delta <= window and delta < best_delta:
                best = neg
                best_delta = delta

        if best is not None:
            transfer_ids.add(pos.id)
            transfer_ids.add(best.id)
            used.add(pos.id)
            used.add(best.id)

    return transfer_ids
