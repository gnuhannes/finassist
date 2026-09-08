"""Heuristic-based recurring transaction detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import RecurringPattern, Transaction
from my_private_finances.utils.money import money_from_db

logger = logging.getLogger(__name__)

# Frequency definitions: (label, target_days, min_days, max_days)
FREQUENCIES: list[tuple[str, int, int, int]] = [
    ("weekly", 7, 4, 10),
    ("monthly", 30, 25, 38),
    ("quarterly", 91, 75, 110),
    ("yearly", 365, 340, 395),
]


@dataclass
class DetectedPattern:
    """Pure data class for a detected recurring pattern (no DB dependency)."""

    payee: str
    typical_amount: Decimal
    frequency: str
    confidence: Decimal
    last_seen: date
    occurrence_count: int
    category_id: int | None


def _median_decimal(values: list[Decimal]) -> Decimal:
    """Compute median of Decimal values without float conversion."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return sorted_vals[n // 2]
    mid = n // 2
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def _detect_frequency(intervals: list[int]) -> tuple[str, Decimal] | None:
    """Match intervals to a known frequency, returning (label, confidence) or None."""
    if not intervals:
        return None

    best: tuple[str, Decimal] | None = None
    best_conf = Decimal("0")

    for label, _target, min_d, max_d in FREQUENCIES:
        matching = sum(1 for gap in intervals if min_d <= gap <= max_d)
        if matching == 0:
            continue
        conf = Decimal(str(matching)) / Decimal(str(len(intervals)))
        if conf > best_conf:
            best_conf = conf
            best = (label, conf)

    return best


def detect_patterns_from_transactions(
    groups: dict[str, list[tuple[date, Decimal, int | None]]],
    min_occurrences: int = 3,
    min_confidence: Decimal = Decimal("0.6"),
) -> list[DetectedPattern]:
    """Pure heuristic: detect recurring patterns from grouped transactions.

    Args:
        groups: mapping of normalized payee -> list of (booking_date, amount, category_id)
        min_occurrences: minimum number of transactions to consider
        min_confidence: minimum confidence threshold

    Returns:
        list of DetectedPattern objects
    """
    results: list[DetectedPattern] = []

    for payee, txns in groups.items():
        if len(txns) < min_occurrences:
            continue

        # Sort by date
        txns_sorted = sorted(txns, key=lambda t: t[0])
        dates = [t[0] for t in txns_sorted]
        amounts = [abs(t[1]) for t in txns_sorted]

        # Compute intervals in days
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

        freq_result = _detect_frequency(intervals)
        if freq_result is None:
            continue

        frequency, interval_confidence = freq_result

        # Check amount consistency: coefficient of variation
        med_amount = _median_decimal(amounts)
        if med_amount == 0:
            continue

        deviations = [abs(a - med_amount) for a in amounts]
        avg_deviation = Decimal(sum(deviations)) / len(deviations)
        amount_cv = avg_deviation / med_amount

        # Boost confidence if amounts are consistent
        if amount_cv <= Decimal("0.05"):
            amount_bonus = Decimal("0.15")
        elif amount_cv <= Decimal("0.10"):
            amount_bonus = Decimal("0.10")
        elif amount_cv <= Decimal("0.20"):
            amount_bonus = Decimal("0.05")
        else:
            amount_bonus = Decimal("0")

        confidence = min(interval_confidence + amount_bonus, Decimal("1.00"))

        if confidence < min_confidence:
            continue

        # Most common category_id
        cat_ids = [t[2] for t in txns_sorted if t[2] is not None]
        category_id = max(set(cat_ids), key=cat_ids.count) if cat_ids else None

        results.append(
            DetectedPattern(
                payee=payee,
                typical_amount=med_amount,
                frequency=frequency,
                confidence=confidence,
                last_seen=dates[-1],
                occurrence_count=len(txns_sorted),
                category_id=category_id,
            )
        )

    return results


async def fetch_transaction_groups(
    session: AsyncSession,
    account_id: int,
) -> dict[str, list[tuple[date, Decimal, int | None]]]:
    """Fetch and group expense transactions by normalized payee."""
    tx = cast(Any, Transaction).__table__

    stmt = (
        select(
            func.lower(func.trim(tx.c.payee)).label("norm_payee"),
            tx.c.booking_date,
            tx.c.amount,
            tx.c.category_id,
        )
        .where(
            (tx.c.account_id == account_id)
            & (tx.c.amount < 0)
            & (tx.c.payee.isnot(None))
        )
        .order_by(tx.c.payee, tx.c.booking_date)
    )

    rows = (await session.execute(stmt)).all()

    groups: dict[str, list[tuple[date, Decimal, int | None]]] = {}
    for r in rows:
        payee = str(r.norm_payee)
        entry = (r.booking_date, money_from_db(r.amount), r.category_id)
        groups.setdefault(payee, []).append(entry)

    return groups


async def run_detection(
    session: AsyncSession,
    account_id: int,
    min_occurrences: int = 3,
    min_confidence: Decimal = Decimal("0.6"),
) -> list[RecurringPattern]:
    """Run recurring detection and upsert patterns into DB."""
    groups = await fetch_transaction_groups(session, account_id)
    logger.info(
        "Recurring detection for account_id=%d: %d payee groups to analyse",
        account_id,
        len(groups),
    )
    detected = detect_patterns_from_transactions(
        groups, min_occurrences, min_confidence
    )
    logger.info(
        "Recurring detection for account_id=%d: %d patterns detected",
        account_id,
        len(detected),
    )

    # Load existing patterns for this account to preserve user overrides
    existing_stmt = select(RecurringPattern).where(
        RecurringPattern.account_id == account_id  # type: ignore[arg-type]
    )
    existing_rows = (await session.execute(existing_stmt)).scalars().all()
    existing_map: dict[tuple[str, str], RecurringPattern] = {
        (p.payee.lower().strip(), p.frequency): p for p in existing_rows
    }

    # Track which patterns we've seen in this run
    seen_keys: set[tuple[str, str]] = set()

    result: list[RecurringPattern] = []
    for det in detected:
        key = (det.payee, det.frequency)
        seen_keys.add(key)

        existing = existing_map.get(key)
        if existing is not None:
            # Update existing pattern, preserving user overrides
            existing.typical_amount = det.typical_amount
            existing.confidence = det.confidence
            existing.last_seen = det.last_seen
            existing.occurrence_count = det.occurrence_count
            existing.category_id = det.category_id
            if not existing.user_confirmed:
                existing.is_active = True
            result.append(existing)
        else:
            pattern = RecurringPattern(
                account_id=account_id,
                payee=det.payee,
                typical_amount=det.typical_amount,
                frequency=det.frequency,
                confidence=det.confidence,
                last_seen=det.last_seen,
                occurrence_count=det.occurrence_count,
                category_id=det.category_id,
            )
            session.add(pattern)
            result.append(pattern)

    # Mark stale patterns as inactive (unless user_confirmed)
    for key, existing in existing_map.items():
        if key not in seen_keys and not existing.user_confirmed:
            existing.is_active = False
            logger.debug(
                "Stale pattern marked inactive: payee=%r, frequency=%s", key[0], key[1]
            )

    await session.commit()
    for p in result:
        await session.refresh(p)

    logger.info(
        "Recurring detection for account_id=%d: %d patterns upserted",
        account_id,
        len(result),
    )
    return result
