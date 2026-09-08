# ADR 0005: Testing Strategy

Date: 2026-09-08
Status: Accepted

***

## Context

The project uses [ECC (Everything Claude Code)](https://github.com/affaan-m/ECC)
for AI-assisted development. ECC's baseline testing rule requires three test
layers — unit, integration, and end-to-end — with browser E2E treated as
mandatory.

Until now this repo had two layers:

- **Backend:** pytest, including HTTP-level API tests via `httpx.AsyncClient` +
  `ASGITransport` (integration coverage without a running server).
- **Frontend:** Vitest + Testing Library (component and hook behaviour, jsdom).

There was no test that exercised the real frontend against the real backend, so
regressions in the wiring between them — the Vite proxy, API base paths,
serialization, routing — could only be caught by hand.

## Decision

Adopt a **browser E2E layer using Playwright**, owned by the frontend package.

### Scope and layering

| Layer | Tool | Location | Runs in |
|---|---|---|---|
| Backend unit + API | pytest (`AsyncClient`) | `api/tests/` | `make ci` |
| Frontend unit/component | Vitest + Testing Library | `app/tests/` | `make ci` |
| End-to-end | Playwright (Chromium) | `app/e2e/` | `make e2e` — separate CI job |

E2E is **not** part of `make ci`. It is heavier (boots the backend and frontend,
needs a browser binary) and runs as its own GitHub Actions job so it does not
slow the inner loop or the main CI gate.

### How it runs

`playwright.config.ts` starts the full stack via `webServer`:

- the FastAPI backend on port 5179 against a throwaway SQLite DB
  (`api/.e2e/e2e.sqlite`, gitignored), migrated with `alembic upgrade head` on
  every run;
- the Vite dev server on port 5173, which proxies `/api` to the backend.

Tests seed their own state through the API and assert against the rendered UI.

### Current coverage

One smoke journey (`app/e2e/smoke.spec.ts`): seed an account, confirm the app
shell renders from live API data, confirm client-side routing works. This is a
deliberate seed, not the finished layer.

### Where it grows

Priority journeys to add next, in order:

1. CSV import → transactions appear in the list
2. Import → categorization rule applied → dashboard reflects it
3. Multi-account net-worth view

When the desktop app (product feature 110, Tauri) lands, revisit whether E2E
should also drive the packaged desktop shell rather than only the browser.

## Consequences

- CI gains a second required job (`e2e`). Total CI time increases; the fast
  `ci` job is unchanged.
- `@playwright/test` is a frontend dev dependency; contributors run
  `pnpm exec playwright install chromium` once. Documented in CONTRIBUTING.md.
- The privacy/local-first posture is unaffected — the E2E stack is entirely
  local, no external services.
- ECC's "E2E required" expectation is now met with a real, if small, layer
  instead of a documented exception.
