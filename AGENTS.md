# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Philosophy and Methodology

### Foundational Philosophy

- Do the right thing because it’s the right thing
- Leave it better than when you found it
- Coding is an art form; go make art

### Development Methodology

- Measure twice and cut once — if you are unsure, confirm before proceeding
- Smart code is better than clever code — prioritize clarity and maintainability
- Start simple, add complexity only when needed
- One change at a time — explain your reasoning

### AI-Specific Constraints

- When in doubt, ask — don’t assume
- Respect existing patterns before suggesting new ones
- Working software beats perfect documentation
- Use the established tech stack unless there’s a compelling reason to change

### Session Hygiene

- Clean up after yourself — remove scripts and artifacts that are no longer necessary
- Turn off the lights when leaving a room — close connections, shut down servers, leave the environment ready for the
  next developer

## Project Overview

**My Private Finances** — a local-first, privacy-by-design personal finance app. No cloud, no telemetry, no external
APIs. All data stays in a local SQLite database.

Core flow: bank statement → CSV import → visualization → insights.

## Repository Structure

Monorepo with two main packages:

- `api/` — Python backend (FastAPI + SQLModel + SQLite)
- `app/` — React frontend (Vite + TypeScript + React Query)
- `docs/adr/` — Architecture Decision Records

## Commands

All commands run from the repo root via Makefiles.

### Full CI (runs both backend and frontend)

```
make ci
```

### Backend (api/)

```
make lint            # ruff check + format check
make lint-fix        # ruff auto-fix + format (from api/ directory: make -C api lint-fix)
make typecheck       # mypy
make test            # pytest
make test-cov        # pytest with coverage report
make coverage        # pytest with 75% minimum coverage gate
make migrate         # alembic upgrade head
make check-migrations # detect schema drift via autogenerate
```

Run a single backend test:

```
cd api && poetry run pytest tests/path/to/test_file.py::test_name -v
```

### Frontend (app/)

```
make fe-lint         # eslint
make fe-typecheck    # tsc
make fe-format-check # prettier check
make fe-test         # vitest
```

Run a single frontend test:

```
cd app && pnpm run test -- tests/path/to/test_file.test.ts
```

### Dev Servers

```
make -C api run      # uvicorn on port 5179
make -C app run      # vite dev on port 5173 (proxies /api to backend)
```

### Dependency Installation

```
make sync            # install backend (poetry) + frontend (pnpm) deps
```

## Architecture

### Backend (`api/my_private_finances/`)

- `main.py` — FastAPI app factory
- `db.py` — async SQLAlchemy engine + session creation
- `deps.py` — FastAPI dependency injection (provides AsyncSession)
- `models/` — SQLModel domain models (Account, Transaction, Category)
- `schemas/` — Pydantic request/response schemas
- `services/` — business logic (CSV import, transaction hashing)
- `api/router.py` — aggregates all route modules
- `api/routes/` — endpoint handlers
- `cli/` — CLI tools (CSV import)

Key conventions:

- Async everywhere (AsyncSession, aiosqlite)
- `Transaction(account_id, import_hash)` is UNIQUE for dedup
- `import_hash` is SHA256, computed in `services/transaction_hash.py`
- Tests use `SQLModel.metadata.create_all` (NOT Alembic) for schema setup
- Decimal type for money amounts (never floats)

### Frontend (`app/src/`)

Layered architecture (enforced by ESLint `import/no-restricted-paths`):

```
pages/       → orchestration (can import from all layers below)
components/  → reusable UI components
hooks/       → React Query wrappers (useAccounts, useMonthlyReport)
lib/api/     → fetch wrapper + API client functions (NO React imports)
domain/      → DTO mappers + domain logic (pure functions)
utils/       → pure helper functions (e.g., formatCurrency)
```

Dependency direction: pages → components/hooks → lib → domain → utils. Never import upward.

Key conventions:

- React Query (TanStack) for server state
- CSS Modules for component styling
- Recharts for data visualization
- Zod for schema validation

### Frontend-Backend Connection

- Vite dev proxy: `/api` → `http://127.0.0.1:5179`
- API base path: `/api/`

## Database

- SQLite at `data/my_private_finances.sqlite` (local, gitignored)
- Migrations: Alembic (`api/alembic/versions/`)
- CI uses separate DB at `api/.ci/my_private_finances.sqlite`
- After model changes, create a migration: `cd api && poetry run alembic revision --autogenerate -m "description"`

## Code Quality Tools

| Tool     | Scope    | Purpose                     |
|----------|----------|-----------------------------|
| Ruff     | Backend  | Linting + formatting        |
| MyPy     | Backend  | Type checking               |
| ESLint   | Frontend | Linting + import rules      |
| Prettier | Frontend | Formatting                  |
| Vitest   | Frontend | Testing                     |
| Pytest   | Backend  | Testing (asyncio_mode=auto) |

## Package Managers

- Backend: Poetry (`api/pyproject.toml`, venv at `api/.venv`)
- Frontend: pnpm (`app/package.json`)
- Node version: 20.x (`.nvmrc`)
