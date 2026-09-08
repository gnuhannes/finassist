# Security Policy

This document describes how to report security issues related to "My Private Finances".

***

## Scope

"My Private Finances" is an early-stage project.

The following components are considered in scope:
- Backend API (api/)
- Frontend application (app/)
- Local data handling and storage
- Build and CI configuration

Third-party dependencies are considered in scope only insofar as they are used
by this project.

***

## Supported Versions

Currently, only the main branch is actively supported.

Security fixes will be applied to main.
No backports are provided at this stage.

***

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

Preferred contact:

Email: johannes@wissmann.dev

Please include:
- A description of the issue
- Steps to reproduce (if possible)
- Potential impact
- Any relevant logs or screenshots

Do not open a public GitHub issue for security-sensitive reports.

***

## Security Model

The current design assumes a **single trusted user on a single trusted
machine**. It is stated explicitly here so that changes which break the
assumption are recognised as security-relevant.

### What we rely on

| Control | Where | What it assumes |
|---|---|---|
| **Loopback bind only** | the API is served on `127.0.0.1` (dev: Vite proxies `/api` to it; desktop: PyInstaller sidecar on localhost) | nothing else on the machine is hostile; no other local user is untrusted |
| **No authentication — by design** | there is no login, session, or API key | the OS user account *is* the security boundary; anyone who can reach the socket is authorised |
| **Explicit CORS allow-list** | `Settings.cors_origins` (default `localhost:5173` / `127.0.0.1:5173`) | the browser enforces same-origin / CORS rules; the SPA runs from an allowed origin |
| **Confirmation header on destructive endpoints** | `X-Requested-With` required for `POST /api/restore/sqlite`, `DELETE /api/data`, `DELETE /api/data/transactions` (see [#99]) | a cross-site page cannot set a custom header on a *simple* request without a CORS preflight, which the allow-list rejects |
| **SQLite foreign keys enforced** | `PRAGMA foreign_keys=ON` per connection | — |
| **Local-only data flow** | no telemetry; no outbound requests except explicit CSV imports the user starts and dependency downloads at build time | the user does not paste a malicious file path / URL |
| **Path-traversal guard** | watch-folder importer refuses files resolving outside the data root | — |

### What breaks this model (do not do these without adding auth first)

- **Binding to `0.0.0.0` or a LAN address.** Every endpoint becomes reachable
  by anything on the network. There is no authentication to fall back on.
- **Serving the SPA and API to a browser on another device** (the PWA / LAN
  roadmap item, [feature 130](docs/product/130-pwa-lan-access.md)). This is
  **gated on adding authentication** (at minimum a shared secret / token, more
  likely per-device credentials) and on re-reviewing every state-changing
  endpoint for CSRF.
- **Adding a reverse proxy / tunnel** (ngrok, Cloudflare Tunnel, etc.) in front
  of the API — same as binding publicly.
- **Widening `cors_origins`** to `*` or to origins not under the user's
  control.
- **Running the process as a shared service account** on a multi-user host —
  the "OS user is the boundary" assumption no longer holds.

### Out of scope (accepted)

- Encryption at rest of the SQLite file — it is the user's own disk.
- Rate limiting / brute-force protection — there is nothing to brute-force.
- Audit logging of reads — single-user.

[#99]: https://github.com/gnuhannes/my-private-finances/issues/99

***

## Design Notes

- Minimise attack surface by operating locally; no user data leaves the machine
  by default.
- Dependencies are pinned and audited in CI (`pip-licenses`, `npm audit` /
  `pnpm audit`, Dependabot).
- The data layer deliberately uses bare-integer foreign keys with no ORM
  relationships — see [ADR 0006](docs/adr/0006-bare-integer-foreign-keys.md).
- Contributors: keep the assumptions above in mind; a change that touches the
  bind address, auth, CORS, or a destructive endpoint needs a note in the PR.