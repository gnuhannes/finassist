import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Transaction
from my_private_finances.schemas.import_result import ImportErrorDetail
from my_private_finances.services.categorization import (
    load_rules_ordered,
    match_transaction,
)
from my_private_finances.services.transaction_hash import compute_import_hash, HashInput

logger = logging.getLogger(__name__)

IMPORT_SOURCE = "csv"


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


@dataclass(slots=True)
class ImportResult:
    total_rows: int
    created: int
    skipped: int
    duplicates: int
    failed: int
    errors: list[ImportErrorDetail] = field(default_factory=list)
    errors_truncated: bool = False


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
        return Decimal(normalized)
    except InvalidOperation:
        raise ValueError(f"Invalid decimal value: '{raw}'")


def _row_fingerprint(row: dict[str, Any]) -> str:
    """
    Deterministic fallback external_id if none is provided.
    Must be stable across re-imports of the same CSV content.
    """
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
    col: ColumnMap = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
    res = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
    if res.scalar_one_or_none() is None:
        raise ValueError(f"Account {account_id} not found")

    rules = await load_rules_ordered(session)
    logger.info(
        "CSV import started: account_id=%d, file=%s, rules=%d",
        account_id,
        csv_path.name,
        len(rules),
    )

    total_rows = 0
    created = 0
    skipped = 0
    duplicates = 0
    failed = 0
    all_errors: list[ImportErrorDetail] = []

    _ENCODINGS = ("utf-8-sig", "cp1252")
    raw = csv_path.read_bytes()
    text: str | None = None
    used_encoding: str | None = None
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(
            f"Cannot decode CSV file — tried {', '.join(_ENCODINGS)}. "
            "Please re-export with UTF-8 encoding."
        )
    logger.debug("CSV encoding detected: %s", used_encoding)

    # Phase 1: parse all rows into Transaction objects; count parse errors
    pending: list[Transaction] = []
    seen_hashes: set[str] = set()

    def _record_error(err: ImportErrorDetail) -> None:
        if len(all_errors) < max_errors:
            all_errors.append(err)
        logger.warning(
            "Line %s: [%s] %s",
            err.row,
            err.field or "?",
            err.message,
        )

    with io.StringIO(text) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        for idx, row in enumerate(reader, start=2):
            total_rows += 1
            if total_rows > max_rows:
                raise ValueError(
                    f"CSV exceeds the {max_rows:,}-row import limit; "
                    "split the file and import in parts"
                )

            if row_filters and any(
                row.get(col, "") not in vals for col, vals in row_filters.items()
            ):
                skipped += 1
                continue
            if row_exclude_filters and any(
                row.get(col, "") in vals for col, vals in row_exclude_filters.items()
            ):
                skipped += 1
                continue

            row_failed = False

            # --- booking_date ---
            booking_date_raw = _first_present(row, col["booking_date"])
            if booking_date_raw is None:
                candidates = "/".join(col["booking_date"])
                _record_error(
                    ImportErrorDetail(
                        row=idx,
                        field="booking_date",
                        message=f"Missing column '{candidates}'",
                        hint="Add one of these header names to the CSV, or configure a column mapping in your profile.",
                    )
                )
                failed += 1
                continue
            try:
                booking_date = _parse_date(booking_date_raw, date_format=date_format)
            except ValueError as e:
                other_fmt = (
                    "DMY (dd.mm.yyyy)" if date_format == "iso" else "ISO (yyyy-mm-dd)"
                )
                _record_error(
                    ImportErrorDetail(
                        row=idx,
                        field="booking_date",
                        raw_value=booking_date_raw,
                        message=str(e),
                        hint=f"Try switching the date format to {other_fmt}.",
                    )
                )
                failed += 1
                row_failed = True

            if row_failed:
                continue

            # --- amount ---
            amount_raw = _first_present(row, col["amount"])
            if amount_raw is None:
                col_in_header = any(k in row for k in col["amount"])
                if col_in_header:
                    # Column header present but cell is empty — informational/pending row, skip silently.
                    skipped += 1
                else:
                    candidates = "/".join(col["amount"])
                    _record_error(
                        ImportErrorDetail(
                            row=idx,
                            field="amount",
                            message=f"Missing column '{candidates}'",
                            hint="Add one of these header names to the CSV, or configure a column mapping in your profile.",
                        )
                    )
                    failed += 1
                continue
            try:
                amount = _parse_decimal(amount_raw, decimal_comma=decimal_comma)
            except ValueError as e:
                decimal_hint = (
                    "Try enabling the 'Decimal comma' option (German format: 1.234,56)."
                    if not decimal_comma
                    else "Try disabling the 'Decimal comma' option (standard format: 1234.56)."
                )
                _record_error(
                    ImportErrorDetail(
                        row=idx,
                        field="amount",
                        raw_value=amount_raw,
                        message=str(e),
                        hint=decimal_hint,
                    )
                )
                failed += 1
                continue

            # --- currency ---
            currency_raw = _first_present(row, col["currency"])
            if currency_raw is None:
                candidates = "/".join(col["currency"])
                _record_error(
                    ImportErrorDetail(
                        row=idx,
                        field="currency",
                        message=f"Missing column '{candidates}'",
                        hint="Add one of these header names to the CSV, or configure a column mapping in your profile.",
                    )
                )
                failed += 1
                continue
            currency = _normalize_currency(currency_raw)

            payee = _first_present(row, col["payee"])
            purpose = _first_present(row, col["purpose"])
            notes = _first_present(row, col["notes"])

            external_id = _first_present(row, col["external_id"])
            if external_id is None:
                external_id = _row_fingerprint(row)

            try:
                import_hash = compute_import_hash(
                    HashInput(
                        account_id=account_id,
                        booking_date=booking_date,
                        amount=amount,
                        currency=currency,
                        payee=payee,
                        purpose=purpose,
                        external_id=external_id,
                        import_source=IMPORT_SOURCE,
                    )
                )
            except Exception as e:
                _record_error(
                    ImportErrorDetail(
                        row=idx,
                        message=f"Failed to compute import hash: {e}",
                        unexpected=True,
                    )
                )
                failed += 1
                continue

            if import_hash in seen_hashes:
                duplicates += 1
                logger.debug("Row %d: within-file duplicate, skipped", idx)
                continue
            seen_hashes.add(import_hash)

            db_obj = Transaction(
                account_id=account_id,
                booking_date=booking_date,
                amount=amount,
                currency=currency,
                payee=payee,
                purpose=purpose,
                notes=notes,
                category_id=None,
                external_id=external_id,
                import_source=IMPORT_SOURCE,
                import_hash=import_hash,
            )

            if rules:
                matched_cat = match_transaction(db_obj, rules)
                if matched_cat is not None:
                    db_obj.category_id = matched_cat

            pending.append(db_obj)

    # Phase 2: filter out rows already in DB, then batch-insert the rest
    if pending:
        pending_hashes = {tx.import_hash for tx in pending}
        existing_result = await session.execute(
            select(Transaction.import_hash).where(  # type: ignore[call-overload]
                Transaction.account_id == account_id,  # type: ignore[arg-type]
                Transaction.import_hash.in_(pending_hashes),  # type: ignore[attr-defined]
            )
        )
        existing_hashes = {row[0] for row in existing_result}
        duplicates += len(existing_hashes)

        new_transactions = [
            tx for tx in pending if tx.import_hash not in existing_hashes
        ]
        if new_transactions:
            session.add_all(new_transactions)
            await session.commit()
        created = len(new_transactions)

    logger.info(
        "CSV import complete: account_id=%d, total=%d, created=%d, skipped=%d, duplicates=%d, failed=%d",
        account_id,
        total_rows,
        created,
        skipped,
        duplicates,
        failed,
    )

    errors_truncated = failed > len(all_errors)
    return ImportResult(
        total_rows=total_rows,
        created=created,
        skipped=skipped,
        duplicates=duplicates,
        failed=failed,
        errors=all_errors,
        errors_truncated=errors_truncated,
    )
