from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
from fastapi.concurrency import run_in_threadpool
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from my_private_finances.config import get_settings
from my_private_finances.models import Category, Transaction
from my_private_finances.schemas.ml import Suggestion, TrainResult

logger = logging.getLogger(__name__)

MIN_SAMPLES = 10


class ColdStartError(Exception):
    """Raised when there are not enough categorized transactions to train."""


def _model_path() -> Path:
    return get_settings().ml_model_path


def _feature_text(tx: Transaction) -> str:
    parts = [tx.payee or "", tx.purpose or ""]
    return " ".join(parts).strip()


def _fit_and_save(texts: list[str], labels: list[Any], model_path: Path) -> None:
    """CPU-bound: fit the pipeline and persist it. Runs in a worker thread."""
    pipeline: Pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    sublinear_tf=True, analyzer="char_wb", ngram_range=(2, 5)
                ),
            ),
            ("clf", CalibratedClassifierCV(LinearSVC())),
        ]
    )
    pipeline.fit(texts, labels)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)


def _load_and_predict(model_path: Path, texts: list[str]) -> tuple[Any, Any]:
    """CPU/IO-bound: load the model and score *texts*. Runs in a worker thread."""
    pipeline: Pipeline = joblib.load(model_path)
    predicted_ids = pipeline.predict(texts)
    confidence_scores = pipeline.predict_proba(texts).max(axis=1)
    return predicted_ids, confidence_scores


async def train(session: AsyncSession) -> TrainResult:
    """Query categorized transactions, fit ML pipeline, persist to disk."""
    result = await session.execute(
        select(Transaction).where(Transaction.category_id.isnot(None))  # type: ignore[union-attr]
    )
    transactions = list(result.scalars().all())

    if len(transactions) < MIN_SAMPLES:
        raise ColdStartError(
            f"Need at least {MIN_SAMPLES} categorized transactions to train "
            f"(found {len(transactions)})"
        )

    texts = [_feature_text(tx) for tx in transactions]
    labels = [tx.category_id for tx in transactions]

    await run_in_threadpool(_fit_and_save, texts, labels, _model_path())

    num_categories = len(set(labels))
    logger.info(
        "ml_categorization.train: trained on %d samples, %d categories",
        len(transactions),
        num_categories,
    )
    return TrainResult(num_samples=len(transactions), num_categories=num_categories)


async def suggest(session: AsyncSession) -> list[Suggestion]:
    """Load trained model and return category suggestions for uncategorized transactions."""
    model_path = _model_path()
    if not model_path.exists():
        raise ColdStartError("No trained model found. Run /ml/train first.")

    # Load uncategorized transactions
    result = await session.execute(
        select(Transaction).where(Transaction.category_id.is_(None))  # type: ignore[union-attr]
    )
    transactions = list(result.scalars().all())

    if not transactions:
        return []

    # Load categories for name lookup
    cat_result = await session.execute(select(Category))
    categories = {cat.id: cat for cat in cat_result.scalars().all()}

    texts = [_feature_text(tx) for tx in transactions]
    predicted_ids, confidence_scores = await run_in_threadpool(
        _load_and_predict, model_path, texts
    )

    suggestions: list[Suggestion] = []
    for tx, cat_id, confidence in zip(transactions, predicted_ids, confidence_scores):
        if tx.id is None:
            continue
        cat = categories.get(cat_id)
        if cat is None:
            continue
        assert cat.id is not None
        suggestions.append(
            Suggestion(
                transaction_id=tx.id,
                category_id=cat.id,
                category_name=cat.name,
                confidence=float(confidence),
                payee=tx.payee,
                purpose=tx.purpose,
                amount=tx.amount,
                booking_date=tx.booking_date,
            )
        )

    logger.info(
        "ml_categorization.suggest: produced %d suggestions for %d uncategorized transactions",
        len(suggestions),
        len(transactions),
    )
    return suggestions
