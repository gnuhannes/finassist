from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.deps import SessionDep
from my_private_finances.models import Account, Transaction
from my_private_finances.models.transfer_candidate import TransferCandidate
from my_private_finances.schemas import TransferCandidateRead, TransferLeg
from my_private_finances.services.transfer_detection import (
    confirm_transfer,
    detect_transfer_candidates,
    dismiss_transfer,
)
from my_private_finances.utils.sql import table

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _build_candidate_read(
    candidate: TransferCandidate,
    txs: dict[int, Transaction],
    accs: dict[int, Account],
) -> TransferCandidateRead:
    assert candidate.id is not None
    from_tx = txs.get(candidate.from_transaction_id)
    to_tx = txs.get(candidate.to_transaction_id)
    if from_tx is None or to_tx is None:
        raise HTTPException(
            status_code=500, detail="Transfer candidate references missing transaction"
        )
    from_acc = accs.get(from_tx.account_id)
    to_acc = accs.get(to_tx.account_id)
    return TransferCandidateRead(
        id=candidate.id,
        from_leg=TransferLeg(
            transaction_id=from_tx.id,  # type: ignore[arg-type]
            account_id=from_tx.account_id,
            account_name=from_acc.name if from_acc else f"Account {from_tx.account_id}",
            booking_date=from_tx.booking_date,
            amount=from_tx.amount,
            payee=from_tx.payee,
        ),
        to_leg=TransferLeg(
            transaction_id=to_tx.id,  # type: ignore[arg-type]
            account_id=to_tx.account_id,
            account_name=to_acc.name if to_acc else f"Account {to_tx.account_id}",
            booking_date=to_tx.booking_date,
            amount=to_tx.amount,
            payee=to_tx.payee,
        ),
        confidence=candidate.confidence,
        status=candidate.status,
    )


async def _load_related(
    session: AsyncSession,
    candidates: list[TransferCandidate],
) -> tuple[dict[int, Transaction], dict[int, Account]]:
    """Batch-load all transactions and accounts referenced by the given candidates."""
    tx_ids = {c.from_transaction_id for c in candidates} | {
        c.to_transaction_id for c in candidates
    }
    txs: dict[int, Transaction] = {}
    if tx_ids:
        rows = await session.execute(
            select(Transaction).where(Transaction.id.in_(tx_ids))  # type: ignore[union-attr]
        )
        txs = {t.id: t for t in rows.scalars().all() if t.id is not None}

    acc_ids = {t.account_id for t in txs.values()}
    accs: dict[int, Account] = {}
    if acc_ids:
        acc_rows = await session.execute(
            select(Account).where(Account.id.in_(acc_ids))  # type: ignore[union-attr]
        )
        accs = {a.id: a for a in acc_rows.scalars().all() if a.id is not None}

    return txs, accs


async def _candidate_to_read(
    session: AsyncSession,
    candidate: TransferCandidate,
) -> TransferCandidateRead:
    txs, accs = await _load_related(session, [candidate])
    return _build_candidate_read(candidate, txs, accs)


@router.post("/detect", response_model=list[TransferCandidateRead], status_code=200)
async def trigger_detection(
    session: SessionDep,
) -> list[TransferCandidateRead]:
    """Detect inter-account transfer candidates across all accounts."""
    new_candidates = await detect_transfer_candidates(session)
    await session.commit()

    # Reload with IDs after commit
    tc = table(TransferCandidate)
    stmt = (
        select(tc)
        .where(tc.c.status == "pending")
        .order_by(tc.c.id.desc())
        .limit(len(new_candidates) if new_candidates else 1)
    )
    _ = await session.execute(stmt)

    for candidate in new_candidates:
        await session.refresh(candidate)
    txs, accs = await _load_related(session, new_candidates)
    return [_build_candidate_read(c, txs, accs) for c in new_candidates]


@router.get("/candidates", response_model=list[TransferCandidateRead])
async def list_candidates(
    session: SessionDep,
    status: Annotated[str | None, Query()] = None,
) -> list[TransferCandidateRead]:
    """List transfer candidates. Defaults to pending if no status filter given."""
    tc = table(TransferCandidate)
    stmt = select(tc)
    filter_status = status if status is not None else "pending"
    stmt = stmt.where(tc.c.status == filter_status).order_by(tc.c.id)

    rows = (await session.execute(stmt)).all()

    candidates = [
        TransferCandidate(
            id=row.id,
            from_transaction_id=row.from_transaction_id,
            to_transaction_id=row.to_transaction_id,
            confidence=row.confidence,
            status=row.status,
        )
        for row in rows
    ]
    txs, accs = await _load_related(session, candidates)
    return [_build_candidate_read(c, txs, accs) for c in candidates]


@router.post("/candidates/{candidate_id}/confirm", response_model=TransferCandidateRead)
async def confirm_candidate(
    candidate_id: int,
    session: SessionDep,
) -> TransferCandidateRead:
    """Confirm a transfer candidate: marks both transactions as is_transfer=True."""
    candidate = await session.get(TransferCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Transfer candidate not found")
    if candidate.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Candidate already {candidate.status}"
        )

    await confirm_transfer(session, candidate)
    await session.commit()
    await session.refresh(candidate)
    return await _candidate_to_read(session, candidate)


@router.post("/candidates/{candidate_id}/dismiss", response_model=TransferCandidateRead)
async def dismiss_candidate(
    candidate_id: int,
    session: SessionDep,
) -> TransferCandidateRead:
    """Dismiss a transfer candidate so it won't be re-suggested."""
    candidate = await session.get(TransferCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Transfer candidate not found")
    if candidate.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Candidate already {candidate.status}"
        )

    await dismiss_transfer(session, candidate)
    await session.commit()
    await session.refresh(candidate)
    return await _candidate_to_read(session, candidate)
