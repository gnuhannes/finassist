# AGENTS.md

Project-specific guidance for AI coding agents (Claude Code, Codex) working on
**My Private Finances**.

Generic engineering practice — TDD, conventional commits, security checklists,
code-quality review, agent orchestration — comes from ECC (Everything Claude
Code) and its skills. This file only records what is specific to this repository.
**When ECC guidance and this file disagree, this file wins.**

> `AGENTS.md` is the single instruction file for this repo. `CLAUDE.md` is
> intentionally git-ignored — do not create one; Claude Code reads `AGENTS.md`.

## Non-negotiable constraints

- **Local-first, privacy by design.** No cloud, no telemetry, no analytics, no
  third-party APIs, no outbound network requests at runtime. All data stays in a
  local SQLite database.
- A new runtime dependency that phones home, or any network call added to `api/`
  or `app/` runtime code, is a design violation — stop and flag it.
- Core flow: bank statement → CSV import → visualization → insights.

## Layout

Monorepo:

- `api/` — Python backend (FastAPI + SQLModel + SQLite, fully async)
- `app/` — React frontend (Vite + TypeScript + React 19 + TanStack Query)
- `docs/adr/` — Architecture Decision Records (read before changing architecture)
- `docs/product/` — vision, roadmap, and per-feature specs

## Commands

All targets run from the repo root via Makefiles.

```
make ci               # full backend + frontend CI
make sync             # install backend (poetry) + frontend (pnpm) deps
```

Backend (`api/`):

```
make lint             # ruff check + ruff format --check
make lint-fix         # ruff --fix + ruff format
make typecheck        # mypy
make test             # pytest
make test-cov         # pytest + coverage report (no gate)
make coverage         # pytest, fails under MIN_COVERAGE (default 75)
make migrate          # alembic upgrade head
make check-migrations # fail if alembic autogenerate detects schema drift
cd api && poetry run pytest tests/path/to/test_file.py::test_name -v   # single test
```

Frontend (`app/`):

```
make fe-lint          # eslint
make fe-typecheck     # tsc --noEmit
make fe-format-check  # prettier --check
make fe-test          # vitest run
cd app && pnpm run test -- tests/path/to/file.test.ts                  # single test
```

E2E (`app/e2e/`, Playwright — not part of `make ci`):

```
make e2e              # boots api + app, runs Playwright (Chromium)
cd app && pnpm exec playwright install chromium                        # one-time
```

Dev servers:

```
make -C api run       # uvicorn on port 5179
make -C app run       # vite dev on port 5173 (proxies /api → 127.0.0.1:5179)
```

## Backend conventions (`api/my_private_finances/`)

Module map: `main.py` app factory · `db.py` async engine/session · `deps.py`
DI (provides `AsyncSession`) · `models/` SQLModel domain models · `schemas/`
Pydantic request/response · `services/` business logic · `api/router.py`
aggregates `api/routes/` · `cli/` CSV import tools.

- **Async everywhere** — `AsyncSession`, `aiosqlite`. Never call sync/blocking
  I/O from a route.
- **Money is `Decimal`, never `float`.**
- `Transaction(account_id, import_hash)` is UNIQUE — this is the import dedup
  key. `import_hash` is a SHA256 computed in `services/transaction_hash.py`.
- Tests build the schema with `SQLModel.metadata.create_all`, **not** Alembic.
- `Transaction.booking_date` must be a `date` object (not a string) when a row is
  constructed directly in a test.
- pytest runs with `asyncio_mode=auto`.

## Database & migrations

- SQLite at `data/my_private_finances.sqlite` (gitignored). CI uses a separate
  DB at `api/.ci/my_private_finances.sqlite`.
- Alembic migrations live in `api/alembic/versions/`; see `docs/migrations.md`.
- After any model change: `cd api && poetry run alembic revision --autogenerate
  -m "description"`, review the file, and commit it. `make check-migrations`
  gates schema drift in CI.
- Autogenerate emits `sqlmodel.sql.sqltypes.AutoString()` — replace it with
  `sa.String()` in the migration (otherwise ruff F821).

## Frontend conventions (`app/src/`)

Layered architecture; dependency direction is enforced by ESLint
`import/no-restricted-paths`:

```
pages/       → orchestration (may import from any layer below)
components/  → reusable UI          hooks/ → TanStack Query wrappers
lib/api/     → fetch wrapper + API client functions (no React imports)
domain/      → DTO mappers + pure domain logic     utils/ → pure helpers
```

Never import upward. `lib/api.ts` is a barrel that re-exports the per-module
clients; hooks import from `../lib/api/<module>` directly.

- TanStack Query for server state · CSS Modules for styling · Recharts for
  charts · Zod for schema validation · i18next for copy.
- API base path is `/api/`.

## Tooling — where ECC defaults do not apply

- **Ruff is the sole Python linter and formatter** (config in `api/pyproject.toml`:
  `line-length` 88, import sorting via lint rule `I`). Do not add black, isort, or
  flake8. Third-party missing-stub handling goes in `[[tool.mypy.overrides]]`, not
  inline `# type: ignore[import-untyped]`.
- Backend: Poetry (venv at `api/.venv`). Frontend: pnpm. Node **24** (`.nvmrc`).
- Backend coverage gate is **`MIN_COVERAGE` in `api/Makefile`** (currently 76%),
  ratcheting toward ECC's 80% target. Never lower it; raise it when coverage
  climbs. New code should land with tests.
- **Test layers:** pytest (backend unit + API via `AsyncClient`) and vitest
  (frontend) run in `make ci`. Playwright E2E (`app/e2e/`) is a separate
  `make e2e` / CI job — keep it out of `make ci`. Strategy + roadmap:
  `docs/adr/0005-testing-strategy.md`.
- Linter/formatter config files are fixed; fix the code, not the config.
