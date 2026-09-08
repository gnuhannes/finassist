# CONTRIBUTING.md
## Contributing to "My Private Finances"

Thanks for your interest in contributing to "My Private Finances"!
"My Private Finances" is a local-first, privacy-respecting personal finance assistant.

***

### Repository Structure

This repository is a monorepo:
- api/ Python backend (FastAPI, Poetry, local SQLite)
- app/ Frontend (React, Vite, pnpm)
- docs/ Architecture decisions and development documentation

Each subproject is set up independently.

***

### Prerequisites

Backend:
- Python 3.11 or newer
- Poetry

Frontend:
- Node.js 24 LTS
- pnpm (recommended via Corepack or nvm)

A `.nvmrc` file is provided in the repository root.

***

### Backend Development (api/)

Setup:

```bash
cd api
poetry install
```

Run the API locally:

```bash
poetry run uvicorn my_private_finances.main:app --reload --port 5179
```

Run checks:

```bash
poetry run ruff check .
poetry run mypy my_private_finances
poetry run pytest
```

Or use the Makefile targets from the repo root:

```bash
make lint        # ruff
make typecheck   # mypy
make test        # pytest
make ci          # all backend + frontend checks
```

***

### Frontend Development (app/)

Setup:

```bash
cd app
pnpm install
```

Run the dev server:

```bash
pnpm dev
```

Run checks:

```bash
pnpm lint
pnpm build
```

pnpm may block some postinstall scripts for security reasons.
If this happens, run:

```bash
pnpm approve-builds
pnpm rebuild
```

***

### End-to-end tests (Playwright)

E2E tests live in `app/e2e/` and boot the real backend + frontend. They are
**not** part of `make ci` — run them separately:

```bash
cd app
pnpm exec playwright install chromium   # one-time
cd ..
make e2e
```

Requires Poetry (backend) and pnpm (frontend) set up. See
`docs/adr/0005-testing-strategy.md`.

***

### Contributing Workflow
1. Fork the repository 
2. Create a feature branch from main (no direct commits to main)
3. Make your changes
4. Ensure CI passes locally (backend and frontend)
5. Open a pull request

***

### Code Style
- Backend: follow Ruff and MyPy checks 
- Frontend: follow ESLint rules 
- Prefer small, focused commits
- Clear and descriptive commit messages are appreciated

***

### License

By contributing to this project, you agree that your contributions
will be licensed under the MIT License, without additional terms.