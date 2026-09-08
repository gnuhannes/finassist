"""Tests for recurring transaction detection heuristics."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, RecurringPattern, Transaction
from my_private_finances.services.recurring_detection import (
    detect_patterns_from_transactions,
    run_detection,
)

# ── Pure heuristic tests (no DB) ──


def _monthly_group(
    payee: str = "netflix",
    base_amount: Decimal = Decimal("-12.99"),
    months: int = 6,
    start: date = date(2025, 7, 1),
) -> dict[str, list[tuple[date, Decimal, int | None]]]:
    """Build a group of monthly transactions."""
    txns = []
    for i in range(months):
        d = date(start.year, start.month + i, start.day)
        txns.append((d, base_amount, 1))
    return {payee: txns}


def test_detect_monthly_pattern() -> None:
    groups = _monthly_group()
    results = detect_patterns_from_transactions(groups)

    assert len(results) == 1
    p = results[0]
    assert p.payee == "netflix"
    assert p.frequency == "monthly"
    assert p.typical_amount == Decimal("12.99")
    assert p.occurrence_count == 6
    assert p.confidence >= Decimal("0.6")


def test_detect_weekly_pattern() -> None:
    base = date(2026, 1, 5)
    txns = [(base + timedelta(weeks=i), Decimal("-25.00"), None) for i in range(8)]
    groups = {"gym": txns}

    results = detect_patterns_from_transactions(groups)

    assert len(results) == 1
    assert results[0].frequency == "weekly"
    assert results[0].typical_amount == Decimal("25.00")


def test_no_pattern_for_random_intervals() -> None:
    txns = [
        (date(2026, 1, 1), Decimal("-50.00"), None),
        (date(2026, 1, 15), Decimal("-30.00"), None),
        (date(2026, 3, 22), Decimal("-45.00"), None),
        (date(2026, 5, 3), Decimal("-60.00"), None),
    ]
    groups = {"random shop": txns}

    results = detect_patterns_from_transactions(groups)

    assert len(results) == 0


def test_min_occurrences_threshold() -> None:
    # Only 2 transactions — should not detect
    txns = [
        (date(2026, 1, 1), Decimal("-10.00"), None),
        (date(2026, 2, 1), Decimal("-10.00"), None),
    ]
    groups = {"spotify": txns}

    results = detect_patterns_from_transactions(groups, min_occurrences=3)
    assert len(results) == 0


def test_amount_tolerance_varying_amounts() -> None:
    """Slightly varying amounts should still be detected."""
    txns = [
        (date(2026, 1, 1), Decimal("-99.00"), None),
        (date(2026, 2, 1), Decimal("-101.00"), None),
        (date(2026, 3, 1), Decimal("-100.00"), None),
        (date(2026, 4, 1), Decimal("-98.50"), None),
        (date(2026, 5, 1), Decimal("-100.50"), None),
    ]
    groups = {"electricity": txns}

    results = detect_patterns_from_transactions(groups)

    assert len(results) == 1
    assert results[0].frequency == "monthly"


def test_confidence_boosted_by_consistent_amounts() -> None:
    # All same amount — should get a confidence bonus
    txns = [
        (date(2026, 1, 1) + timedelta(days=30 * i), Decimal("-9.99"), None)
        for i in range(6)
    ]
    groups = {"spotify": txns}

    results = detect_patterns_from_transactions(groups)
    assert len(results) == 1
    assert results[0].confidence > Decimal("0.7")


def test_category_id_most_common() -> None:
    txns = [
        (date(2026, 1, 1), Decimal("-10.00"), 5),
        (date(2026, 2, 1), Decimal("-10.00"), 5),
        (date(2026, 3, 1), Decimal("-10.00"), 3),
        (date(2026, 4, 1), Decimal("-10.00"), 5),
    ]
    groups = {"streaming": txns}

    results = detect_patterns_from_transactions(groups)
    assert len(results) == 1
    assert results[0].category_id == 5


# ── Integration tests with DB ──


async def _seed_account(session: AsyncSession) -> Account:
    acc = Account(name="Main", currency="EUR")
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def _seed_monthly_transactions(
    session: AsyncSession,
    account_id: int,
    payee: str,
    amount: str,
    months: int = 6,
) -> None:
    for i in range(months):
        tx = Transaction(
            account_id=account_id,
            booking_date=date(2026, 1 + i, 5),
            amount=Decimal(amount),
            currency="EUR",
            payee=payee,
            purpose="recurring",
            import_source="manual",
            import_hash=f"rec-{payee}-{i}",
        )
        session.add(tx)
    await session.commit()


@pytest.mark.asyncio
async def test_run_detection_creates_patterns(db_session: AsyncSession) -> None:
    acc = await _seed_account(db_session)
    await _seed_monthly_transactions(db_session, acc.id, "Netflix", "-12.99")  # type: ignore[arg-type]

    patterns = await run_detection(db_session, acc.id)  # type: ignore[arg-type]

    assert len(patterns) >= 1
    netflix = [p for p in patterns if p.payee == "netflix"]
    assert len(netflix) == 1
    assert netflix[0].frequency == "monthly"
    assert netflix[0].is_active is True


@pytest.mark.asyncio
async def test_run_detection_preserves_user_confirmed(
    db_session: AsyncSession,
) -> None:
    acc = await _seed_account(db_session)
    await _seed_monthly_transactions(db_session, acc.id, "Netflix", "-12.99")  # type: ignore[arg-type]

    # First detection
    patterns = await run_detection(db_session, acc.id)  # type: ignore[arg-type]
    assert len(patterns) >= 1

    # User confirms
    p = patterns[0]
    p.user_confirmed = True
    await db_session.commit()

    # Re-run detection — should preserve user_confirmed
    patterns2 = await run_detection(db_session, acc.id)  # type: ignore[arg-type]
    confirmed = [pp for pp in patterns2 if pp.user_confirmed]
    assert len(confirmed) >= 1


@pytest.mark.asyncio
async def test_run_detection_marks_stale_inactive(
    db_session: AsyncSession,
) -> None:
    acc = await _seed_account(db_session)
    await _seed_monthly_transactions(db_session, acc.id, "Netflix", "-12.99")  # type: ignore[arg-type]

    # First detection
    patterns = await run_detection(db_session, acc.id)  # type: ignore[arg-type]
    assert len(patterns) >= 1

    # Delete all transactions (simulate pattern going stale)
    from sqlmodel import delete

    await db_session.execute(delete(Transaction))
    await db_session.commit()

    # Re-run detection — stale pattern should be deactivated
    patterns2 = await run_detection(db_session, acc.id)  # type: ignore[arg-type]
    # No new patterns returned (no data)
    assert len(patterns2) == 0

    # The old pattern should be marked inactive
    from sqlmodel import select

    all_patterns = (await db_session.execute(select(RecurringPattern))).scalars().all()
    assert len(all_patterns) == 1
    assert all_patterns[0].is_active is False
