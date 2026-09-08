# Architecture & Code Review — 2026-09-08

Reviewed at `main` @ `91d26ef`. Scope: backend (`api/`, ~4.8k LOC), frontend
(`app/src/`, ~5.7k LOC), dependencies, security posture.

Focus: design, maintainability by a solo human developer, clean-code paradigms,
security, outdated packages.

**Derived tasks:** milestone
[*Post-review hardening (2026-09)*](https://github.com/gnuhannes/my-private-finances/milestone/1),
issues **#96–#116** (mapping in [§5](#5-task-index)).

## Summary

The codebase is in **good overall health** for a solo project. Layering is
clear and enforced, tests are meaningful (backend ~76% coverage), error handling
does not swallow failures, and there are no secrets or SQL-injection issues.

The main themes to address:

1. **Type-safety escape hatches** (`cast(Any, X).__table__`, ~19 uses) and
   **hand-written response mappers** (`_to_read` in every route) are systemic
   friction that a schema-driven approach removes.
2. **The async contract is violated** — CSV parsing, ML training, and SQLite
   backup/restore all run CPU/IO-bound work directly on the event loop.
3. **Data-integrity gaps** — SQLite foreign keys are never enabled; no
   `created_at`/`updated_at`; money aggregation round-trips through `float`.
4. **Security is "localhost + no auth + no CORS" by convention only** — several
   endpoints (wipe, restore, import) are unauthenticated and CSRF-exposed, which
   is fine today but blocks the PWA/LAN (feature 130) and desktop (110) plans
   without hardening.
5. **Dependency hygiene** — `react-router` is 12 advisories behind; `pandas` and
   `zod` are declared but unused; backend version pins are so tight they fight
   Dependabot.

Severity legend: **S1** critical / **S2** important / **S3** minor-but-worth-doing.

---

## 1. Architecture & Design

### A1 (S2) — Reporting SQL lives in the route layer, not services

`api/routes/reports.py` (297 LOC), `trends.py`, `annual.py`, `net_worth.py`,
`transfers.py` build all their SQL inline in the endpoint function. The
`services/` layer is bypassed for exactly the queries that are hardest to test
and most likely to change. `csv_import`, `categorization`, `recurring_detection`,
`transfer_detection` correctly live in `services/` — reporting should too.

**Impact:** route functions are 50–80 lines of query-building; the aggregation
logic can only be tested through HTTP; duplication (see C4) has nowhere to live.

**Direction:** introduce `services/reporting.py` with functions returning typed
result objects; routes become thin adapters.

### A2 (S2) — The async contract is violated by CPU/IO-bound work

`AGENTS.md` states "async everywhere … never call sync/blocking I/O from a
route", but:

- `services/csv_import.py` — `csv.DictReader` parse loop + per-row `hashlib`
  over the whole file runs on the event loop. A 50k-row import freezes every
  other request for its duration.
- `services/ml_categorization.py` — `pipeline.fit()` / `joblib.dump/load` are
  synchronous and CPU-heavy.
- `routes/export.py`, `routes/data_management.py` — `sqlite3.Connection.backup()`
  copies up to 500 MB synchronously inside the request.

**Direction:** wrap the bodies in `anyio.to_thread.run_sync` /
`fastapi.concurrency.run_in_threadpool`. For CSV, parse in a worker thread and
only touch the `AsyncSession` back on the loop.

### A3 (S2) — Three overlapping data-location mechanisms

- `config.get_data_dir()` → `DATA_DIR` env (used by ML model + watch folders)
- `db.DEFAULT_DB_PATH` → hard-coded `Path("data")` (used as the DB default)
- `db.get_database_url()` → `DATABASE_URL` env (overrides the DB only)

Consequences:
- Setting `DATA_DIR` moves the ML model and watch dirs but **not** the database.
- `routes/export.py` / `data_management.py` back up / restore
  `request.app.state.db_path` (= `DEFAULT_DB_PATH`), which is **not** the file in
  use when `DATABASE_URL` is set → export produces a stale/empty file, restore
  writes to the wrong path. **This is a latent data-loss bug** (also C11).

**Direction:** one `Settings` object (pydantic-settings) that derives
`database_url`, `data_dir`, `model_path`, `watch_root` from a single `DATA_DIR` +
optional `DATABASE_URL` override, injected via `app.state` and used everywhere.

### A4 (S3) — No ORM relationships; every join is hand-rolled

No `Relationship()` anywhere. FKs are bare `int` fields; lookups are manual
`session.get` calls or dict-building (`{cat.id: cat for …}` appears repeatedly).
This is a defensible choice for async SQLModel (avoids lazy-load traps), but it
should be a **documented ADR decision**, and the read-heavy paths (reports,
suggestions) pay for it with N+1-ish patterns and boilerplate.

### A5 (S3) — Frontend/backend types are hand-maintained in parallel

Backend Pydantic schemas and `app/src/lib/api/*.ts` types are written twice and
already drift (`ImportResult` in `imports.ts` is missing `skipped`; see C9).
`zod` is a declared dependency but **used nowhere** — there is no runtime
validation of any API response.

**Direction:** generate the TS client/types from the backend OpenAPI schema
(`openapi-typescript` or `orval`) in CI, or adopt zod schemas as the single
source and infer types from them. Either kills the drift class entirely.

### A6 (S3) — Module-level app construction hurts testability

`main.py` ends with `app = create_app()`, which builds an engine at import time.
`create_app(db_path=…)` takes a parameter that is only logged — the engine
ignores it and calls `get_database_url()` itself. Tests must monkeypatch or set
env before import.

**Direction:** make `create_app` accept the resolved settings and wire them to
the engine; keep the module-level `app` for uvicorn but let tests call
`create_app(test_settings)`.

### A7 (S3) — Background watcher has no supervision

`main.py` starts one `watch_folder_task`. Per-file errors are caught inside
`_process_file`, but an exception raised in `watch_folder_task` itself (e.g.
observer thread failure, `queue` handling) kills the task silently — no restart,
no health signal. Consider a supervisor wrapper that logs + relaunches, and
expose watcher status on `/health`.

---

## 2. Clean Code / Maintainability

### C1 (S2) — `cast(Any, Model).__table__` escape hatch (19 uses, 8 files)

Used to get a Core `Table` and silence mypy on SQLModel column expressions.
Every reporting/detection module opens with
`tx = cast(Any, Transaction).__table__`. It defeats the type checker exactly
where the queries are most complex.

**Direction:** upgrade `sqlmodel` (0.0.31 → 0.0.42 fixes many typing issues),
then use model columns directly with narrowly-scoped `# type: ignore` where
still needed, or a typed `columns()` helper. Track the count down to zero.

### C2 (S2) — Hand-written response mappers everywhere

`_to_read(...)` exists in `accounts`, `categories`, `budgets`, `csv_profiles`,
`categorization_rules`, `recurring_patterns`; `transactions.py` inlines a
13-field `TransactionRead(...)` constructor **three times** (create, update,
list). Pure boilerplate that drifts.

**Direction:** give the `*Read` schemas `model_config =
ConfigDict(from_attributes=True)` and return `Schema.model_validate(db_obj)` (or
set `response_model` and return the ORM object). Removes ~150 lines and a whole
class of "forgot to map the new field" bugs.

### C3 (S2) — `Decimal(str(<float from SQLite>))` (18 uses)

SQLite stores `Numeric` as REAL, so `SUM()` returns a float and the code does
`Decimal(str(row.total))` to recover it. `str(0.1 + 0.2)` still carries the
float error into the `Decimal`, so **money aggregations can be a cent off**.

**Direction:** register a SQLAlchemy `TypeDecorator` / connection cast so
`Numeric` round-trips as `Decimal`, **or** compute sums in Python from
`Decimal` columns, **or** accept and document a rounding step. At minimum,
extract a single `_to_decimal()` helper instead of 18 call sites.

### C4 (S2) — Duplicated filter-building in reporting routes

The `if account_id is not None: base_filter = … else: base_filter = …` block and
`transfer_filter = tx.c.is_transfer == False  # noqa: E712` are copy-pasted
across `reports.py` (×3), `trends.py`, `annual.py`, `net_worth.py`. Extract
`month_expense_filter(account_id, start, end)` once (belongs in `services/`
per A1).

### C5 (S2) — HTTP status decided by string-matching exception messages

`routes/imports.py`: `if "not found" in msg: raise HTTPException(404) …`. Fragile
— a reworded message silently changes the status code.

**Direction:** define typed exceptions in `services/` (`AccountNotFoundError`,
`CsvFormatError`, …) and map them to status codes in one exception handler or a
small `@app.exception_handler` registry.

### C6 (S2) — `services/csv_import.py::import_transactions_from_csv_path` is 275 lines

One function does: account check, rule load, encoding detection, a ~180-line
per-row parse/validate/hash/dedup loop, and a two-phase insert. High cyclomatic
complexity, hard to unit-test a single concern.

**Direction:** extract `parse_row(row, cfg) -> ParsedRow | RowError`,
`detect_encoding(bytes) -> str`, and a `RowAccumulator`. The loop body becomes a
dispatch over `parse_row` results.

### C7 (S2) — PATCH semantics broken in `update_transaction`

`db_obj.category_id = payload.category_id` is unconditional, so
`PATCH /transactions/{id}` with `{}` (or any body where `category_id` is unset)
**clears the category**. PATCH should treat an absent field as "no change".
Use `payload.model_dump(exclude_unset=True)`.

### C8 (S2) — `category_filter` only understands the literal `"uncategorized"`

`routes/transactions.py::list_transactions` — any other value is silently
ignored, so there is no way to filter the list by a specific category id.
Either implement it or remove the half-feature.

### C9 (S1-for-correctness) — Frontend/backend type drift is already real

`app/src/lib/api/imports.ts::ImportResult` omits `skipped`, which the backend
returns. Because responses are cast (`body as T`) with no validation, this is
invisible until a user notices wrong numbers. Fix the immediate drift and adopt
A5.

### C10 (S3) — Dead code / unused declarations

- `db.py::get_session(session_factory)` — never imported (the real one is
  `deps.py::get_session`).
- `routes/health.py` — defines `/health` but the router is **not** registered in
  `api/router.py`. Either wire it up (useful for the desktop app / watchdog) or
  delete it.
- `pandas` — declared in `api/pyproject.toml`, imported **nowhere**. Removing it
  drops a large transitive tree (important for the PyInstaller sidecar in
  feature 110).
- `zod` — declared in `app/package.json`, used nowhere (see A5).

### C11 (S2) — export/restore target the wrong DB file

See A3. `routes/export.py::export_sqlite` and
`routes/data_management.py::restore_sqlite` use `request.app.state.db_path`
(= `DEFAULT_DB_PATH`), not the engine's actual URL. With `DATABASE_URL` set,
export backs up the wrong/empty file and restore overwrites the wrong path.

### C12 (S3) — Decimal parsing accepts `NaN` / `Infinity` / scientific notation

`services/csv_import.py::_parse_decimal` and
`services/categorization.py::_match_amount` do `Decimal(value)`, which happily
returns `Decimal("NaN")`, `Decimal("Infinity")`, `Decimal("1E10")`. A malformed
CSV cell or rule value slips through as a non-finite amount.
Add `if not parsed.is_finite(): raise ValueError`.

### C13 (S3) — Inconsistencies that add friction

- Return-type annotations present on most endpoints, missing on
  `accounts.py::create_account` / `list_accounts`, `health.py::health`.
- `Query()` annotation used on some list params, omitted on
  `transactions.py::list_transactions`'s `date_from`, `category_filter`, `q`.
- `StrictSchema` (`extra="forbid"`) used for some `*Create` schemas, plain
  `BaseModel` for `*Read` and others — pick one policy.
- Import ordering in `api/router.py` is unsorted and mixes
  `from … import reports` with `from ….x import router as x_router`.
  *(PR #94 enables ruff import-sort, which fixes the ordering.)*
- `_move_to_processed` / `_move_to_failed` in `watch_folder.py` duplicate the
  unique-destination loop.
- `deps.py` and `db.py` both define `get_session`.

### C14 (S3) — Frontend

- `lib/api/client.ts` sets `Content-Type: application/json` on **every** request
  including GET; `imports.ts` reimplements `fetch` + `ApiError` handling a third
  time (also in `apiDelete`). Consolidate into one `apiFetch`.
- No request timeout / `AbortController` anywhere — a hung backend hangs the UI.
- Hard-coded English strings leak past i18n, e.g. `NetWorth.tsx` `" as of "`.
- `import React, { useState }` — the `React` import is unnecessary under the
  new JSX runtime.
- Test coverage is thin: 10 test files for ~40 components/pages. Backend has 43.

### C15 (S3) — No audit columns

No model has `created_at` / `updated_at`. For a finance app that ingests and
mutates transaction data, "when was this row imported / last edited" is
valuable and cheap to add now (one migration, `server_default=func.now()`).

---

## 3. Security

Context: the app is **local-first, single-user, no authentication by design**,
and uvicorn binds `127.0.0.1` by default. The findings below matter (a) against
a malicious local process, (b) against CSRF from any website the user visits
while the app runs, and (c) as blockers for the **PWA/LAN (feature 130)** and
**desktop (feature 110)** roadmap items.

### SEC1 (S2) — SQLite foreign keys are never enabled

No `PRAGMA foreign_keys = ON` and no `connect` event listener. Every
`foreign_key=` / `ondelete` in the models is **not enforced at runtime**. You
can insert a `Transaction` with a non-existent `account_id`, or leave orphaned
transactions/budgets/rules after deleting a `Category`. The "FK-safe order"
comments in `data_management.py` / `export.py` are aspirational.

**Fix:** add a `connect` event listener that issues `PRAGMA foreign_keys=ON`
per connection; add explicit `ondelete` behaviour to FKs; add a migration +
data check for existing orphans.

### SEC2 (S2) — Unauthenticated destructive + restore endpoints, CSRF-exposed

- `DELETE /api/data` (wipe everything), `DELETE /api/data/transactions`,
  `POST /api/restore/sqlite` (replace the whole DB), `POST /api/imports/csv`.
- `POST` with `multipart/form-data` is a CORS "simple request": **any web page
  the user has open can POST a CSV or a replacement SQLite file to
  `localhost:5179`** and the browser will send it (the attacker can't read the
  response, but the side effect lands). `DELETE` is preflighted and currently
  blocked by the absence of CORS — but that protection is one
  `CORSMiddleware(allow_origins=["*"])` away from gone.

**Fix:** require a confirmation header/token that a cross-origin simple request
cannot set (e.g. an `X-Requested-With` check, or a per-session token the SPA
reads from a `GET` first), and/or a typed confirmation body
(`{"confirm": "DELETE ALL DATA"}`). Add an explicit `CORSMiddleware` with an
allow-list rather than relying on the default.

### SEC3 (S2) — `restore_sqlite` accepts almost any file

Validation is: `len <= 500 MB` and first 16 bytes == SQLite magic. No
`PRAGMA integrity_check`, no schema check, no alembic-version check. A truncated
or foreign-schema DB silently replaces the live one and the app then fails at
runtime. Also runs `engine.dispose()` + sync `sqlite3.backup` with no lock, so a
concurrent request during restore races on the file.

**Fix:** restore into a temp path, run `PRAGMA integrity_check` and verify
`alembic_version` is a known revision (offer to migrate), then swap atomically
under an app-level lock.

### SEC4 (S2) — Unbounded CSV upload

`routes/imports.py` — `content = await file.read()` with no size cap; the bytes
are then held in memory again by the service. No content-type/extension guard.
`data_management.py` caps restore at 500 MB but import has no cap at all.

**Fix:** reject early on `Content-Length` / `file.size`; stream to the temp file
in chunks; cap row count in the parser.

### SEC5 (S3) — Data-exfiltration surface if CORS is ever relaxed

`GET /api/export/json` and `/api/export/sqlite` return **all** financial data
unauthenticated. Today the same-origin policy stops a remote page from reading
the response. This is the highest-value target the moment CORS, a `0.0.0.0`
bind, or LAN access is introduced. Treat "no auth" as a documented, deliberate
constraint (`SECURITY.md`) and gate feature 130 on adding auth.

### SEC6 (S3) — `react-router` 7.13.1: 12 advisories (6 high)

`pnpm audit` reports 12 advisories, all `react-router`, fixed in ≤ 7.18.2.
Most are SSR/RSC-specific and **do not apply to this SPA**, but a few are
generic (open redirect via backslash in `<Link>`/`useNavigate`; DoS via route
matching). `package.json` already allows `^7.13.1`, so
`pnpm update react-router-dom` → 7.18.3 clears all 12. Low real risk, trivial
fix, and it clears the audit dashboard.

### SEC7 (S3) — `python-multipart` pinned to exactly `0.0.21`

`api/pyproject.toml`: `python-multipart (>=0.0.21,<0.0.22)`. This library parses
every file upload and has had DoS/ReDoS CVEs historically. The pin blocks all
patch updates. Loosen the pin (see D1) and update to 0.0.32.

### SEC8 (S3) — SHA-1 for the row fingerprint

`services/csv_import.py::_row_fingerprint` uses SHA-1. It is not a security
boundary (just a stable fallback id), but for consistency with
`transaction_hash.py` (SHA-256) and to avoid a reviewer flag, switch to SHA-256.

*No secrets, credentials, or SQL injection were found. All DB access is
parameterized via SQLAlchemy Core/ORM. Error handling logs rather than swallows.*

---

## 4. Outdated Packages

### Backend (`api/pyproject.toml`)

| Package | Current | Latest | Note |
|---|---|---|---|
| `python-multipart` | 0.0.21 (pinned `<0.0.22`) | 0.0.32 | SEC7 — upload parser |
| `fastapi` | 0.128 (`<0.129`) | 0.141 | tight pin |
| `starlette` (transitive) | 0.50 | 1.6 | major |
| `uvicorn` | 0.40 (`<0.41`) | 0.52 | tight pin |
| `sqlmodel` | 0.0.31 (`<0.0.32`) | 0.0.42 | fixes typing (C1) |
| `pydantic` | 2.13 | 2.x | ok, minor |
| `mypy` (dev) | 1.20 (`<2.0`) | 2.3 | major |
| `ruff` (dev) | 0.14 (`<0.15`) | 0.16 | *(PR #94 pins config)* |
| `pandas` | 2.3 | 3.0 | **remove — unused (C10)** |

### D1 (S2) — Version pins fight Dependabot

Every runtime dep is pinned `>=X,<X+0.0.1` or `<X+1`. `python-multipart` is
locked to a single patch release. The Dependabot merge history in `git log` is
almost entirely these pins being nudged one patch at a time. Adopt
`>=X,<NEXT_MAJOR` (or Poetry `^X`) for libraries with a stable SemVer track
(`fastapi`, `uvicorn`, `sqlmodel`, `python-multipart`, `alembic`, `httpx`) and
let the lockfile + CI be the gate.

### Frontend (`app/package.json`)

Healthy — most deps are one patch behind. Majors available but not urgent:
`eslint` 9→10, `@vitejs/plugin-react` 5→6, `@testing-library/jest-dom` 6→7,
`@eslint/js` 9→10. **`react-router-dom` 7.13 → 7.18 should be done now** (SEC6).
Remove `zod` or start using it (A5/C10).

---

## 5. Task Index

Grouped PR-sized units. Milestone: *Post-review hardening (2026-09)*.

| Issue | Task | Findings | Sev |
|---|---|---|---|
| [#96](https://github.com/gnuhannes/my-private-finances/issues/96) | Enforce SQLite foreign keys + cascade behaviour | SEC1 | S2 |
| [#97](https://github.com/gnuhannes/my-private-finances/issues/97) | export/restore wrong DB file; harden restore validation | C11, SEC3, A3 | S2 |
| [#98](https://github.com/gnuhannes/my-private-finances/issues/98) | Bound CSV upload size and row count | SEC4 | S2 |
| [#99](https://github.com/gnuhannes/my-private-finances/issues/99) | Confirmation guard + explicit CORS on destructive endpoints | SEC2, SEC5 | S2 |
| [#100](https://github.com/gnuhannes/my-private-finances/issues/100) | Small API-correctness fixes (PATCH, filters, drift, Decimal, hash) | C7, C8, C9, C12, SEC8 | S1–S3 |
| [#101](https://github.com/gnuhannes/my-private-finances/issues/101) | Frontend deps: react-router bump, remove unused deps + dead code | SEC6, C10, D1 | S2–S3 |
| [#102](https://github.com/gnuhannes/my-private-finances/issues/102) | Backend deps: loosen pins, update multipart/fastapi/uvicorn/sqlmodel | D1, SEC7 | S2 |
| [#103](https://github.com/gnuhannes/my-private-finances/issues/103) | Move blocking work off the event loop | A2 | S2 |
| [#104](https://github.com/gnuhannes/my-private-finances/issues/104) | Extract services/reporting.py; dedupe filter-building | A1, C4 | S2 |
| [#105](https://github.com/gnuhannes/my-private-finances/issues/105) | Schema-driven responses: kill _to_read boilerplate | C2, C13 | S2 |
| [#106](https://github.com/gnuhannes/my-private-finances/issues/106) | Reduce cast(Any).__table__ type escape hatch | C1 | S2 |
| [#107](https://github.com/gnuhannes/my-private-finances/issues/107) | Typed service exceptions + centralized HTTP status mapping | C5 | S2 |
| [#108](https://github.com/gnuhannes/my-private-finances/issues/108) | Break up the 275-line csv_import parse function | C6 | S2 |
| [#109](https://github.com/gnuhannes/my-private-finances/issues/109) | Unify configuration into a Settings object | A3, A6 | S2–S3 |
| [#110](https://github.com/gnuhannes/my-private-finances/issues/110) | Add created_at/updated_at audit columns | C15 | S3 |
| [#111](https://github.com/gnuhannes/my-private-finances/issues/111) | Money precision: SQLite Numeric SUM through float | C3 | S2 |
| [#112](https://github.com/gnuhannes/my-private-finances/issues/112) | FE/BE contract: generate TS types from OpenAPI | A5, C10 | S3 |
| [#113](https://github.com/gnuhannes/my-private-finances/issues/113) | Frontend cleanups: fetch wrapper, timeouts, i18n leaks | C14 | S3 |
| [#114](https://github.com/gnuhannes/my-private-finances/issues/114) | Watcher supervision + register /health | A7, C10 | S3 |
| [#115](https://github.com/gnuhannes/my-private-finances/issues/115) | Document security model + ADR for data-layer design | SEC5, SEC2, A4 | S3 |
| [#116](https://github.com/gnuhannes/my-private-finances/issues/116) | Raise frontend test coverage | C14 | S3 |

Suggested order: **#96, #97, #100, #101, #98** (quick wins / correctness /
security) → **#102, #111, #103, #109** (deps + data correctness + config) →
**#104, #105, #106, #107, #108** (backend structure) → **#112, #113, #99, #114,
#110, #115, #116** (contracts, polish, docs).

---

## Appendix — What's already good

- Frontend layering (`pages → components/hooks → lib → domain → utils`) is clean
  and ESLint-enforced; violations are impossible to merge.
- `services/categorization.py` and `services/transaction_hash.py` are exemplary:
  small pure functions, dispatch tables, full typing, no I/O mixed in.
- Money is `Decimal` end-to-end in the models and API (the float issue is only
  in SQLite `SUM()` read-back — C3).
- No swallowed exceptions; background-worker errors are logged with `exc_info`.
- The path-traversal guard in `watch_folder.py` is correct.
- Backend test suite is substantial (43 files, ~76% coverage) and uses real
  HTTP + a real (in-memory-schema) DB.
- Import dedup design (`(account_id, import_hash)` unique + SHA-256 content
  hash + within-file dedup) is sound.
