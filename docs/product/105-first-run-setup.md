# 105 — First-Run Setup 🔜 Planned

## Goal

Guide a brand-new user from an empty database to a usable dashboard: at least one account
with a starting balance, a sensible set of categories, and (optionally) their first
imported statement — without them having to discover the Accounts, Categories, and Import
pages on their own.

## Problem

A fresh install has no accounts, no categories, and no rules. Today the app just renders
bare "no accounts yet" text on every page. The user has to work out, unaided, that they
must:

1. create an account (on the Net Worth page, via an inline editor),
2. set an opening balance and as-of date (a second step — `POST /accounts` doesn't even
   accept the balance; it needs a follow-up `PATCH`),
3. create categories one by one,
4. then find the Import dialog.

This matters more once the app ships as a packaged desktop app (see
[110](110-desktop-app.md)), where the first launch is always a blank database.

The **starting balance** is the sharp edge: Net-Worth tracking ([040](040-net-worth-tracking.md))
only includes accounts that have `opening_balance` + `opening_balance_date` set, and
running balances are meaningless without it. New users don't know to set it.

## Approach

Fully local — no cloud, no telemetry. A full-screen guided wizard shown on first run.

### Trigger & persistence

New singleton table `AppSettings` (`id = 1`, same pattern as `WatchSettings`):

| field | type | purpose |
|---|---|---|
| `onboarding_completed_at` | `datetime \| None` | wizard shown while `None` |
| `onboarding_skipped` | `bool` | distinguishes "skipped" from "finished" |
| `default_currency` | `str` (default `EUR`) | prefilled in the account step, future global default |
| `locale` | `str \| None` | mirrors the language switcher, server-visible |

The Alembic migration's data step sets `onboarding_completed_at = now()` for any database
that **already has ≥ 1 account**, so existing users are never forced through the wizard.

Frontend guard in `App.tsx`: fetch `AppSettings` once on load; if
`onboarding_completed_at is None` and the route isn't `/welcome`, redirect to `/welcome`
and hide the nav bar there. A `?rerun=1` escape hatch lets the "Re-run setup" button in
Settings re-enter the wizard without clearing the timestamp.

### Steps

1. **Welcome & privacy** — restate "all data stays on this machine"; choose language and
   default currency.
2. **First account + starting balance** — name, currency (prefilled), **starting balance**
   and **as-of date** (defaults to today). Copy explains: *"Your balance on this date.
   Anything imported after it adds up from here — this powers Net Worth and running
   balances. Match it to your oldest statement, or use today if you're starting fresh."*
   Repeatable; at least one account required to continue.
3. **Categories** — a preselected, localized starter set (checkbox list) with sensible
   `cost_type` grouping (Rent / Insurance / Subscriptions → fixed; Groceries / Dining /
   Shopping / Transport → variable; Salary / income → none) plus "add your own".
   Skippable.
4. **Import first statement** *(optional)* — inline import form (account + CSV format +
   file), or "I'll do this later". Shows "N imported, M auto-categorized".
5. **Done** — summary ("1 account · €X starting balance · 12 categories · 84 transactions")
   and links to Dashboard / Import / Rules. Stamps `onboarding_completed_at`.

Progress indicator, Back / Next, and a corner "Skip setup" that stamps completion with
`onboarding_skipped = True`. Each step commits immediately via REST, so quitting halfway
still leaves valid data.

### Starter category list

The canonical list (i18n keys + `cost_type` + parent grouping) lives in the frontend
translation files so names are localized (en + de). The backend only stores what it is
given.

## Design Notes

### Backend

- New model `models/app_settings.py` + migration (with the "stamp existing users" data
  step).
- New routes: `GET /settings/app` (create-on-read default), `PATCH /settings/app`.
- Extend `AccountCreate` with optional `opening_balance` + `opening_balance_date`; persist
  them in `create_account`. Useful beyond the wizard — removes the current create-then-patch
  dance.
- New `POST /categories/batch` — accepts `[{name, cost_type?, parent_id?}]`, all-or-nothing,
  returns the created rows.

### Frontend

- `lib/api/appSettings.ts` + `hooks/useAppSettings.ts`.
- Onboarding guard in `App.tsx`; nav bar hidden on `/welcome`.
- `pages/Welcome/WelcomeWizard.tsx` + one component per step + CSS modules.
- Extract the import form out of `ImportDialog`'s `<dialog>` wrapper so it can render inline
  in step 4 (small refactor; `FileDropZone` is already reusable).
- Settings page: "Re-run setup wizard" button → `/welcome?rerun=1`.
- Replace the bare "no accounts yet" texts with a friendly empty state linking to
  `/welcome`.
- i18n: `welcome.*` and `categories.starter.*` keys in `en.json` + `de.json`.

### Tests

- Backend: `test_app_settings.py` (default-on-read, PATCH, flag lifecycle); extend
  `test_accounts.py` (opening balance on create); `test_categories.py` (batch: happy path,
  rollback on bad `parent_id`).
- Frontend: step navigation, guard redirect, "skip" stamps completion.
- E2E (Playwright): fresh DB → complete wizard → land on a populated dashboard.

## Out of Scope (v1)

- Resumable / persisted partial progress.
- Watch-folder setup (stays in Settings).
- Built-in CSV bank-profile presets (separate backlog item — the wizard makes their
  absence more visible).
- Multi-currency / FX.

## Rollout

Three PRs off `main`:

- **A** — backend: `AppSettings` model + migration + `/settings/app` routes;
  `AccountCreate` opening balance; `POST /categories/batch`.
- **B** — frontend: onboarding guard + wizard shell + steps 1–2 (intro + account /
  starting balance).
- **C** — frontend: steps 3–5 (starter categories + optional import + done) + Settings
  "re-run" button + empty-state cleanup + i18n + E2E.

Milestone-aligned with [110 — Desktop App](110-desktop-app.md).

## Definition of Done

- A fresh install redirects to `/welcome` on first launch.
- The user can create an account **with a starting balance in one step**, pick starter
  categories, optionally import a file, and land on a dashboard that already shows data.
- Net Worth includes the new account immediately (opening balance + date are set).
- Existing databases are never forced through the wizard.
- "Re-run setup" is available from Settings.
