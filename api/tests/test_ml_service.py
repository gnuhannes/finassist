from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Category, Transaction
from my_private_finances.services.ml_categorization import (
    ColdStartError,
    suggest,
    train,
)


async def _seed_account(db_session: AsyncSession) -> int:
    account = Account(name="Main", currency="EUR")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    assert account.id is not None
    return account.id


def _make_tx(
    account_id: int,
    import_hash: str,
    category_id: int | None = None,
    payee: str = "REWE",
    purpose: str = "Groceries",
) -> Transaction:
    return Transaction(
        account_id=account_id,
        booking_date=date(2026, 1, 15),
        amount=Decimal("42.00"),
        currency="EUR",
        payee=payee,
        purpose=purpose,
        category_id=category_id,
        import_hash=import_hash,
    )


@pytest.mark.asyncio
async def test_train_insufficient_data_raises_cold_start(
    db_session: AsyncSession,
) -> None:
    # Add fewer than 10 categorized transactions
    account_id = await _seed_account(db_session)
    cat = Category(name="Groceries")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    for i in range(5):
        db_session.add(_make_tx(account_id, f"hash-{i}", category_id=cat.id))
    await db_session.commit()

    with pytest.raises(ColdStartError):
        await train(db_session)


@pytest.mark.asyncio
async def test_train_returns_stats(db_session: AsyncSession, tmp_path: Path) -> None:
    account_id = await _seed_account(db_session)
    cat1 = Category(name="Groceries")
    cat2 = Category(name="Transport")
    db_session.add(cat1)
    db_session.add(cat2)
    await db_session.commit()
    await db_session.refresh(cat1)
    await db_session.refresh(cat2)

    for i in range(6):
        db_session.add(
            _make_tx(account_id, f"hash-g{i}", category_id=cat1.id, payee="REWE")
        )
    for i in range(6):
        db_session.add(
            _make_tx(
                account_id,
                f"hash-t{i}",
                category_id=cat2.id,
                payee="BVG",
                purpose="Transport",
            )
        )
    await db_session.commit()

    model_path = tmp_path / "ml_model.joblib"
    with patch(
        "my_private_finances.services.ml_categorization._model_path",
        return_value=model_path,
    ):
        result = await train(db_session)

    assert result.num_samples == 12
    assert result.num_categories == 2
    assert model_path.exists()


@pytest.mark.asyncio
async def test_suggest_returns_predictions(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    account_id = await _seed_account(db_session)
    cat1 = Category(name="Groceries")
    cat2 = Category(name="Transport")
    db_session.add(cat1)
    db_session.add(cat2)
    await db_session.commit()
    await db_session.refresh(cat1)
    await db_session.refresh(cat2)

    for i in range(6):
        db_session.add(
            _make_tx(account_id, f"hash-g{i}", category_id=cat1.id, payee="REWE")
        )
    for i in range(6):
        db_session.add(
            _make_tx(
                account_id,
                f"hash-t{i}",
                category_id=cat2.id,
                payee="BVG",
                purpose="Transport",
            )
        )
    # Add uncategorized transaction
    db_session.add(
        _make_tx(account_id, "hash-uncat", category_id=None, payee="REWE Markt")
    )
    await db_session.commit()

    model_path = tmp_path / "ml_model.joblib"
    with patch(
        "my_private_finances.services.ml_categorization._model_path",
        return_value=model_path,
    ):
        await train(db_session)
        suggestions = await suggest(db_session)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.category_id in (cat1.id, cat2.id)
    assert 0.0 <= s.confidence <= 1.0
    assert s.payee == "REWE Markt"


@pytest.mark.asyncio
async def test_suggest_no_model_raises(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    missing_path = tmp_path / "nonexistent.joblib"
    with patch(
        "my_private_finances.services.ml_categorization._model_path",
        return_value=missing_path,
    ):
        with pytest.raises(ColdStartError):
            await suggest(db_session)
