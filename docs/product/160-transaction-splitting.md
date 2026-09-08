# 160 — Transaction Splitting 🔜 Planned

## Goal

Let the user split a single bank transaction across several categories — by absolute
amounts or by percentage. The classic case: one standing-order transfer that covers *rent*
plus *utilities / extras*, which today can only land in one category.

## Problem

`Transaction` carries a single nullable `category_id`. A €1,200 rent transfer that is
really €1,000 rent + €200 utilities has to be filed as one or the other, so the monthly
category breakdown, budget-vs-actual, fixed-vs-variable, and spending-trend reports are all
slightly wrong for anyone with combined payments. Workarounds (a fake second transaction, a
catch-all "rent + extras" category) distort totals or lose detail.

This is also the **foundation for [100 — Bill Scanning](100-bill-scanning.md)**: OCR'd
receipt line items are just splits with a receipt attached. Building the split model + report
attribution now means 100 later only adds capture + OCR.

## Approach

### Data model

New child table; `Transaction.category_id` stays as the fast path for the common
single-category case (no migration of existing rows):

```
transaction_split
  id             int  PK
  transaction_id int  FK -> transaction.id   (indexed, ON DELETE CASCADE)
  category_id    int  FK -> category.id       (nullable = an unassigned portion)
  amount         Numeric(14,2)  signed, transaction currency
  note           text  nullable
```

A transaction is **simple** (0 split rows → uses `category_id`) or **split** (≥ 2 rows →
`category_id` forced `NULL`).

### Invariants

- **Split amounts must sum exactly to `transaction.amount`** (signed `Decimal` equality) —
  rejected with 422 otherwise.
- Splitting is **attribution only**. It creates no balance-affecting rows, so net / income /
  expense totals, per-account balance, and net worth are untouched — they still sum
  `transaction.amount`, which never changes.
- Minimum 2 splits. Deleting splits reverts the transaction to simple (leaves `category_id`
  `NULL` — the user re-picks).
- Transfers cannot be split in v1 (already excluded from category reports).

### Absolute vs. relative

Purely a **frontend** concern. The split dialog offers **Amounts** and **Percentages**
modes; in percentage mode it computes the amounts live and drops the leftover cent into the
last row so the sum stays exact. The API only ever receives and stores **absolute** amounts
— no ratio column in v1.

## Design Notes

### Backend

- New `models/transaction_split.py` + Alembic migration (create table, no backfill). The
  `transaction_id` FK is `ondelete="CASCADE"` from the start (aligns with pending cascade
  work, issue #117).
- Routes:
  - `GET /transactions/{id}/splits`
  - `PUT /transactions/{id}/splits` — replace-all; validates ≥ 2 rows, categories exist,
    `Σ amount == tx.amount`, transaction is not a transfer; sets `tx.category_id = NULL`;
    all-or-nothing.
  - `DELETE /transactions/{id}/splits` — revert to simple.
  - `PATCH /transactions/{id}` with `category_id` on a split transaction → **409** ("delete
    splits first"); never silently drop splits.
- `TransactionRead` gains `split_count: int` so the list can badge / expand split rows.
- **Category-attribution selectable** — the core reporting change. A helper in
  `services/reporting.py` (the module issue **#104** extracts) returns a selectable that
  yields one row per `(category_id, amount)` with the transaction columns carried through:

  ```
  splits joined to their transaction
  UNION ALL
  transactions that have no splits   (category_id, amount straight through)
  ```

  Category reports swap `Transaction.__table__` for this selectable; every existing
  `date / account / transfer / amount < 0` filter ports over unchanged. Affected:
  `reports.py` (monthly `category_breakdown`, `budget-vs-actual`, `fixed-vs-variable`) and
  `trends.py` (`spending-trend`). **Unaffected:** `annual.py`, `net_worth.py` (no
  category), and `top_payees` / `top_spendings` (per-transaction, keep the full amount).
- `ml_categorization.py`: `train()` excludes split transactions (ambiguous label) in v1;
  "train on the dominant split" is a later option. `suggest()` already skips them.
- Rules, the `category_filter=uncategorized` list filter, and recurring detection treat a
  split transaction as categorized — add `AND NOT EXISTS (split)` to
  `apply_rules_to_uncategorized` and the uncategorized query.
- `categories.py` delete guard also blocks deletion when a `transaction_split` references
  the category.

### Frontend

- `lib/api/transactionSplits.ts` + `hooks/useTransactionSplits.ts`.
- `components/SplitTransactionDialog.tsx`: rows of (`CategorySelect` + amount + optional
  note + remove); **Amounts / Percentages** toggle; "split evenly" button; live
  "€X of €Y allocated, €Z left"; Save disabled until the sum is exact and there are ≥ 2
  rows; "Remove split".
- `TransactionTable`: split rows show a "Split (N)" chip instead of the inline dropdown, and
  expand to preview the parts.
- i18n `split.*` keys (en + de).
- Reports need **no response-shape changes**.

### Tests

- Backend: `test_transaction_splits.py` (sum validation, ≥ 2 rows, transfer rejected, 409
  on PATCH category, GET / DELETE); report tests (a split transaction lands in the right
  categories across monthly / trends / fixed-vs-variable / budget-vs-actual); category
  delete guard; ML train exclusion; uncategorized filter exclusion; `make check-migrations`
  clean.
- Frontend: percentage ↔ amount conversion and cent rounding, sum gating, save, revert.
- E2E (Playwright): split a transaction 70 / 30 → both categories appear in the monthly
  breakdown.

## Sequencing

PR B below overlaps heavily with issue **#104** (extract `services/reporting.py`, dedupe the
transfer / month filters across `reports.py` and `trends.py`). The attribution selectable
belongs in that same new module. **Do #104 first** (or fold PR B into it); otherwise the
reporting helper gets built twice.

## Rollout

Three PRs off `main`, after #104:

- **A** — `transaction_split` model + migration + splits CRUD + validation + `split_count`
  + category-delete guard. Splits exist but do not yet affect reports.
- **B** — category-attribution selectable in `services/reporting.py`; port monthly / trends
  / fixed-vs-variable / budget-vs-actual; ML / rules / uncategorized-filter exclusions.
- **C** — split dialog (amounts + percentages), table chips, i18n, E2E.

## Out of Scope (v1)

- Splitting transfers.
- Storing percentages / ratios server-side.
- Receipt capture and OCR — that is [100](100-bill-scanning.md), which builds on this.
- Filtering the transaction list by a specific category (not currently supported anyway).

## Definition of Done

- A non-transfer transaction can be split into ≥ 2 category portions by amount or by
  percentage, with the portions required to sum to the transaction total.
- Monthly breakdown, budget-vs-actual, fixed-vs-variable, and spending-trend all attribute
  each portion to its category.
- Net worth, account balances, and income / expense / net totals are unchanged.
- Splits can be edited and removed; removing them reverts the transaction to a single
  category.
