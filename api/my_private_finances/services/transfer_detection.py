"""Transfer detection service.

Detects candidate inter-account transfers by matching transactions across accounts
where:
  - One leg is negative (outgoing) and the other is positive (incoming)
  - abs(amount_A) == abs(amount_B)
  - |date_A - date_B| <= window_days (default 3)
  - The pair is not already tracked in TransferCandidate with any status
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Transaction
from my_private_finances.utils.money import money_from_db
from my_private_finances.models.transfer_candidate import TransferCandidate

logger = logging.getLogger(__name__)


async def detect_transfer_candidates(
    session: AsyncSession,
    window_days: int = 3,
) -> list[TransferCandidate]:
    """Detect inter-account transfer candidates across all accounts.

    Skips pairs that are already in TransferCandidate (any status).
    Returns newly created TransferCandidate rows (status='pending').
    """
    tx = cast(Any, Transaction).__table__
    acc = cast(Any, Account).__table__

    # Load all transactions with account info
    stmt = (
        select(
            tx.c.id,
            tx.c.account_id,
            tx.c.booking_date,
            tx.c.amount,
            tx.c.payee,
        )
        .select_from(tx.join(acc, tx.c.account_id == acc.c.id))
        .order_by(tx.c.booking_date, tx.c.amount)
    )
    rows = (await session.execute(stmt)).all()
    logger.info(
        "Transfer detection started: window_days=%d, transactions=%d",
        window_days,
        len(rows),
    )

    # Split into negative (outgoing) and positive (incoming) buckets
    outgoing = [r for r in rows if r.amount < 0]
    incoming = [r for r in rows if r.amount > 0]

    # Load already-tracked pairs to avoid duplicates
    tc = cast(Any, TransferCandidate).__table__
    existing_stmt = select(tc.c.from_transaction_id, tc.c.to_transaction_id)
    existing_rows = (await session.execute(existing_stmt)).all()
    existing_pairs: set[tuple[int, int]] = {
        (r.from_transaction_id, r.to_transaction_id) for r in existing_rows
    }

    new_candidates: list[TransferCandidate] = []
    window = timedelta(days=window_days)

    for out_tx in outgoing:
        out_abs = abs(money_from_db(out_tx.amount))

        for in_tx in incoming:
            # Must be different accounts
            if out_tx.account_id == in_tx.account_id:
                continue

            # Amount must match exactly
            in_abs = money_from_db(in_tx.amount)
            if out_abs != in_abs:
                continue

            # Date must be within window
            date_diff = abs(out_tx.booking_date - in_tx.booking_date)
            if date_diff > window:
                continue

            # Skip already-tracked pairs
            pair = (out_tx.id, in_tx.id)
            if pair in existing_pairs:
                continue

            # Confidence: starts at 1.0, reduced by 0.1 per day of date spread
            confidence = Decimal("1.0") - Decimal("0.1") * Decimal(str(date_diff.days))
            confidence = max(confidence, Decimal("0.70"))

            candidate = TransferCandidate(
                from_transaction_id=out_tx.id,
                to_transaction_id=in_tx.id,
                confidence=confidence,
                status="pending",
            )
            session.add(candidate)
            new_candidates.append(candidate)
            existing_pairs.add(pair)  # prevent duplicate within same run

    await session.flush()
    logger.info(
        "Transfer detection complete: %d new candidates found", len(new_candidates)
    )
    return new_candidates


async def confirm_transfer(session: AsyncSession, candidate: TransferCandidate) -> None:
    """Mark both transaction legs as transfers and set candidate status to confirmed."""
    candidate.status = "confirmed"

    from_tx = await session.get(Transaction, candidate.from_transaction_id)
    to_tx = await session.get(Transaction, candidate.to_transaction_id)

    if from_tx is not None:
        from_tx.is_transfer = True
    if to_tx is not None:
        to_tx.is_transfer = True

    await session.flush()
    logger.info(
        "Transfer confirmed: candidate_id=%s (tx %s → %s)",
        candidate.id,
        candidate.from_transaction_id,
        candidate.to_transaction_id,
    )


async def dismiss_transfer(session: AsyncSession, candidate: TransferCandidate) -> None:
    """Mark candidate as dismissed so it won't be re-suggested."""
    candidate.status = "dismissed"
    await session.flush()
    logger.info(
        "Transfer dismissed: candidate_id=%s (tx %s → %s)",
        candidate.id,
        candidate.from_transaction_id,
        candidate.to_transaction_id,
    )
