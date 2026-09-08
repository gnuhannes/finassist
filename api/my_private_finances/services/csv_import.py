"""CSV import (review finding C6 / issue #108).

``import_transactions_from_csv_path`` used to be a ~275-line function doing
account check + rule load + encoding detection + a ~180-line per-row loop +
two-phase insert. It's now split:

* :func:`detect_encoding` — bytes -> ``(text, encoding)``.
* :func:`parse_row` — one CSV row -> ``ParsedRow`` | ``RowSkipped`` | ``RowFailed``.
* :class:`RowAccumulator` — counters + bounded error list.
* :func:`parse_csv` — pure, CPU-bound driver over ``parse_row``; runs in a
  worker thread so a big import doesn't stall the event loop (finishes #103).
* ``import_transactions_from_csv_path`` — async shell: DB reads/writes only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, CategorizationRule, Transaction
from my_private_finances.schemas.import_result import ImportErrorDetail
from my_private_finances.services.categorization import (
    load_rules_ordered,
    match_transaction,
)
from my_private_finances.services.exceptions import CsvFormatError, NotFoundError
from my_private_finances.services.transaction_hash import HashInput, compute_import_hash

logger = logging.getLogger(__name__)

IMPORT_SOURCE = "csv"

_ENCODINGS = ("utf-8-sig", "cp1252")


class ColumnMap(TypedDict, total=False):
    booking_date: list[str]
    amount: list[str]
    currency: list[str]
    payee: list[str]
    purpose: list[str]
    external_id: list[str]
    notes: list[str]


DEFAULT_COLUMN_MAP: ColumnMap = {
    "booking_date": ["booking_date", "Buchungstag", "Valutadatum"],
    "amount": ["amount", "Betrag"],
    "currency": ["currency", "Waehrung"],
    "payee": ["payee", "Beguenstigter/Zahlungspflichtiger"],
    "purpose": ["purpose", "Verwendungszweck"],
    "external_id": [
        "external_id",
        "Kundenreferenz (End-to-End)",
        "Sammlerreferenz",
        "Mandatsreferenz",
    ],
    "notes": [],
}

_MISSING_COLUMN_HINT = (
    "Add one of these header names to the CSV, or configure a column mapping "
    "in your profile."
)


@dataclass(slots=True)
class CsvConfig:
    """Resolved import settings for one file (column map already merged)."""

    column_map: ColumnMap
    delimiter: str = ","
    date_format: str = "iso"
    decimal_comma: bool = False
    row_filters: dict[str, list[str]] | None = None
    row_exclude_filters: dict[str, list[str]] | None = None


@dataclass(slots=True)
class ParsedRow:
    booking_date: date
    amount: Decimal
    currency: str
    payee: str | None
    purpose: str | None
    notes: str | None
    external_id: str


@dataclass(slots=True)
class RowSkipped:
    """Row intentionally ignored (filter match, or empty amount cell)."""


@dataclass(slots=True)
class RowFailed:
    error: ImportErrorDetail


RowOutcome = ParsedRow | RowSkipped | RowFailed


@dataclass(slots=True)
class ImportResult:
    total_rows: int
    created: int
    skipped: int
    duplicates: int
    failed: int
    errors: list[ImportErrorDetail] = field(default_factory=list)
    errors_truncated: bool = False


class RowAccumulator:
    """Running counters + a bounded list of row errors for one import."""

    def __init__(self, max_errors: int) -> None:
        self.total_rows = 0
        self.created = 0
        self.skipped = 0
        self.duplicates = 0
        self.failed = 0
        self.errors: list[ImportErrorDetail] = []
        self._max_errors = max_errors

    def record_error(self, err: ImportErrorDetail) -> None:
        self.failed += 1
        if len(self.errors) < self._max_errors:
            self.errors.append(err)
        logger.warning("Line %s: [%s] %s", err.row, err.field or "?", err.message)

    def to_result(self) -> ImportResult:
        return ImportResult(
            total_rows=self.total_rows,
            created=self.created,
            skipped=self.skipped,
            duplicates=self.duplicates,
            failed=self.failed,
            errors=self.errors,
            errors_truncated=self.failed > len(self.errors),
        )


# --------------------------------------------------------------------------- #
# Pure value parsers
# --------------------------------------------------------------------------- #


def _normalize_currency(value: str) -> str:
    return value.strip().upper()


def _parse_date(value: str, date_format: str) -> date:
    raw = value.strip()
    if date_format == "iso":
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"Invalid ISO date: '{raw}'")
    if date_format == "dmy":
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Invalid DMY date: '{raw}'")
    raise ValueError(f"Unsupported date format: {date_format}")


def _parse_decimal(value: str, *, decimal_comma: bool) -> Decimal:
    raw = value.strip()
    normalized = raw.replace(".", "").replace(",", ".") if decimal_comma else raw
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        raise ValueError(f"Invalid decimal value: '{raw}'")
    if not parsed.is_finite():
        raise ValueError(f"Non-finite decimal value: '{raw}'")
    return parsed


def _row_fingerprint(row: dict[str, Any]) -> str:
    """Deterministic fallback external_id — stable across re-imports of the file."""
    parts = [
        str(row.get("booking_date", "")).strip(),
        str(row.get("amount", "")).strip(),
        str(row.get("currency", "")).strip().upper(),
        str(row.get("payee", "") or "").strip(),
        str(row.get("purpose", "") or "").strip(),
    ]
    raw = "\n".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _first_present(row: dict[str, Any], keys: list[str]) -> str | None:
    for k in keys:
        if k in row:
            val = (row.get(k) or "").strip()
            return val or None
    return None


def _missing_column_error(row_num: int, field_name: str, keys: list[str]) -> RowFailed:
    return RowFailed(
        ImportErrorDetail(
            row=row_num,
            field=field_name,
            message=f"Missing column '{'/'.join(keys)}'",
            hint=_MISSING_COLUMN_HINT,
        )
    )


# --------------------------------------------------------------------------- #
# Encoding + row parsing
# --------------------------------------------------------------------------- #


def detect_encoding(raw: bytes) -> tuple[str, str]:
    """Decode CSV bytes — UTF-8 (BOM-aware) then cp1252. Returns ``(text, encoding)``."""
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise CsvFormatError(
        f"Cannot decode CSV file — tried {', '.join(_ENCODINGS)}. "
        "Please re-export with UTF-8 encoding."
    )


def _is_filtered_out(row: dict[str, str], cfg: CsvConfig) -> bool:
    if cfg.row_filters and any(
        row.get(col, "") not in vals for col, vals in cfg.row_filters.items()
    ):
        return True
    if cfg.row_exclude_filters and any(
        row.get(col, "") in vals for col, vals in cfg.row_exclude_filters.items()
    ):
        return True
    return False


def parse_row(row: dict[str, str], row_num: int, cfg: CsvConfig) -> RowOutcome:
    """Turn one raw CSV row into a ``ParsedRow``, or a skip / failure marker."""
    cmap = cfg.column_map

    if _is_filtered_out(row, cfg):
        return RowSkipped()

    booking_date_raw = _first_present(row, cmap["booking_date"])
    if booking_date_raw is None:
        return _missing_column_error(row_num, "booking_date", cmap["booking_date"])
    try:
        booking_date = _parse_date(booking_date_raw, date_format=cfg.date_format)
    except ValueError as e:
        other_fmt = (
            "DMY (dd.mm.yyyy)" if cfg.date_format == "iso" else "ISO (yyyy-mm-dd)"
        )
        return RowFailed(
            ImportErrorDetail(
                row=row_num,
                field="booking_date",
                raw_value=booking_date_raw,
                message=str(e),
                hint=f"Try switching the date format to {other_fmt}.",
            )
        )

    amount_raw = _first_present(row, cmap["amount"])
    if amount_raw is None:
        if any(k in row for k in cmap["amount"]):
            # Header present but the cell is empty — informational / pending row.
            return RowSkipped()
        return _missing_column_error(row_num, "amount", cmap["amount"])
    try:
        amount = _parse_decimal(amount_raw, decimal_comma=cfg.decimal_comma)
    except ValueError as e:
        decimal_hint = (
            "Try enabling the 'Decimal comma' option (German format: 1.234,56)."
            if not cfg.decimal_comma
            else "Try disabling the 'Decimal comma' option (standard format: 1234.56)."
        )
        return RowFailed(
            ImportErrorDetail(
                row=row_num,
                field="amount",
                raw_value=amount_raw,
                message=str(e),
                hint=decimal_hint,
            )
        )

    currency_raw = _first_present(row, cmap["currency"])
    if currency_raw is None:
        return _missing_column_error(row_num, "currency", cmap["currency"])

    return ParsedRow(
        booking_date=booking_date,
        amount=amount,
        currency=_normalize_currency(currency_raw),
        payee=_first_present(row, cmap["payee"]),
        purpose=_first_present(row, cmap["purpose"]),
        notes=_first_present(row, cmap["notes"]),
        external_id=_first_present(row, cmap["external_id"]) or _row_fingerprint(row),
    )


def _build_transaction(
    parsed: ParsedRow,
    account_id: int,
    rules: Sequence[CategorizationRule],
) -> Transaction:
    import_hash = compute_import_hash(
        HashInput(
            account_id=account_id,
            booking_date=parsed.booking_date,
            amount=parsed.amount,
            currency=parsed.currency,
            payee=parsed.payee,
            purpose=parsed.purpose,
            external_id=parsed.external_id,
            import_source=IMPORT_SOURCE,
        )
    )
    tx = Transaction(
        account_id=account_id,
        booking_date=parsed.booking_date,
        amount=parsed.amount,
        currency=parsed.currency,
        payee=parsed.payee,
        purpose=parsed.purpose,
        notes=parsed.notes,
        category_id=None,
        external_id=parsed.external_id,
        import_source=IMPORT_SOURCE,
        import_hash=import_hash,
    )
    if rules:
        matched_cat = match_transaction(tx, list(rules))
        if matched_cat is not None:
            tx.category_id = matched_cat
    return tx


# --------------------------------------------------------------------------- #
# Sync driver (worker thread) + async shell
# --------------------------------------------------------------------------- #


def parse_csv(
    text: str,
    cfg: CsvConfig,
    *,
    account_id: int,
    rules: Sequence[CategorizationRule],
    max_rows: int,
    max_errors: int,
) -> tuple[list[Transaction], RowAccumulator]:
    """CPU-bound: parse every row and build the transient ``Transaction`` list.

    De-duplicates within the file; DB-level de-dup happens back on the loop.
    Runs in a worker thread — must not touch the ``AsyncSession``.
    """
    acc = RowAccumulator(max_errors)
    pending: list[Transaction] = []
    seen_hashes: set[str] = set()

    reader = csv.DictReader(io.StringIO(text), delimiter=cfg.delimiter)
    if reader.fieldnames is None:
        raise CsvFormatError("CSV has no header row")

    for row_num, row in enumerate(reader, start=2):
        acc.total_rows += 1
        if acc.total_rows > max_rows:
            raise CsvFormatError(
                f"CSV exceeds the {max_rows:,}-row import limit; "
                "split the file and import in parts"
            )

        outcome = parse_row(row, row_num, cfg)
        if isinstance(outcome, RowSkipped):
            acc.skipped += 1
            continue
        if isinstance(outcome, RowFailed):
            acc.record_error(outcome.error)
            continue

        try:
            tx = _build_transaction(outcome, account_id, rules)
        except Exception as e:  # pragma: no cover - compute_import_hash is total
            acc.record_error(
                ImportErrorDetail(
                    row=row_num,
                    message=f"Failed to compute import hash: {e}",
                    unexpected=True,
                )
            )
            continue

        if tx.import_hash in seen_hashes:
            acc.duplicates += 1
            logger.debug("Row %d: within-file duplicate, skipped", row_num)
            continue
        seen_hashes.add(tx.import_hash)
        pending.append(tx)

    return pending, acc


async def import_transactions_from_csv_path(
    *,
    session: AsyncSession,
    account_id: int,
    csv_path: Path,
    max_errors: int = 50,
    max_rows: int = 100_000,
    delimiter: str = ",",
    date_format: str = "iso",
    decimal_comma: bool = False,
    column_map: ColumnMap | None = None,
    row_filters: dict[str, list[str]] | None = None,
    row_exclude_filters: dict[str, list[str]] | None = None,
) -> ImportResult:
    res = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
    if res.scalar_one_or_none() is None:
        raise NotFoundError(f"Account {account_id} not found")

    rules = await load_rules_ordered(session)
    cfg = CsvConfig(
        column_map={**DEFAULT_COLUMN_MAP, **(column_map or {})},
        delimiter=delimiter,
        date_format=date_format,
        decimal_comma=decimal_comma,
        row_filters=row_filters,
        row_exclude_filters=row_exclude_filters,
    )

    text, encoding = detect_encoding(csv_path.read_bytes())
    logger.info(
        "CSV import started: account_id=%d, file=%s, rules=%d, encoding=%s",
        account_id,
        csv_path.name,
        len(rules),
        encoding,
    )

    pending, acc = await run_in_threadpool(
        parse_csv,
        text,
        cfg,
        account_id=account_id,
        rules=rules,
        max_rows=max_rows,
        max_errors=max_errors,
    )

    if pending:
        pending_hashes = {tx.import_hash for tx in pending}
        existing_result = await session.execute(
            select(Transaction.import_hash).where(  # type: ignore[call-overload]
                Transaction.account_id == account_id,  # type: ignore[arg-type]
                Transaction.import_hash.in_(pending_hashes),  # type: ignore[attr-defined]
            )
        )
        existing_hashes = {row[0] for row in existing_result}
        acc.duplicates += len(existing_hashes)

        new_transactions = [
            tx for tx in pending if tx.import_hash not in existing_hashes
        ]
        if new_transactions:
            session.add_all(new_transactions)
            await session.commit()
        acc.created = len(new_transactions)

    logger.info(
        "CSV import complete: account_id=%d, total=%d, created=%d, skipped=%d, "
        "duplicates=%d, failed=%d",
        account_id,
        acc.total_rows,
        acc.created,
        acc.skipped,
        acc.duplicates,
        acc.failed,
    )
    return acc.to_result()
