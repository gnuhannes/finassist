.PHONY: help
help:
	@echo "Targets (root):"
	@echo "  make ci            - Run backend + frontend checks"
	@echo "  make ci-backend    - Run backend checks"
	@echo "  make ci-frontend   - Run frontend checks"
	@echo "  make lint          - Backend lint (ruff)"
	@echo "  make typecheck     - Backend typecheck (mypy)"
	@echo "  make test          - Backend tests (pytest)"
	@echo "  make test-cov      - Backend tests with coverage report"
	@echo "  make coverage      - Backend coverage gate (MIN_COVERAGE)"
	@echo "  make migrate       - Apply backend migrations (alembic upgrade head)"
	@echo "  make check-migrations - Fail if alembic autogenerate detects drift"
	@echo "  make fe-lint       - Frontend lint"
	@echo "  make fe-format-check - Frontend prettier check"
	@echo "  make fe-typecheck  - Frontend typecheck"
	@echo "  make fe-test       - Frontend tests (if configured)"
	@echo "  make e2e           - Playwright E2E smoke (boots api + app; not in ci)"
	@echo "  make sync          - Install deps (backend + frontend)"

.PHONY: ci
ci: ci-backend ci-frontend check-openapi
	@echo "✅ Full CI suite passed"

# Regenerate the FE/BE contract: api/openapi.json + app/src/lib/api/schema.d.ts
.PHONY: openapi
openapi:
	cd api && poetry run python scripts/export_openapi.py
	cd app && pnpm run -s gen:api

# Fail if the committed contract is stale (CI).
.PHONY: check-openapi
check-openapi: openapi
	git diff --exit-code -- api/openapi.json app/src/lib/api/schema.d.ts \
		|| { echo "openapi.json / schema.d.ts are out of date — run 'make openapi'"; exit 1; }

.PHONY: ci-backend
ci-backend:
	$(MAKE) -C api ci

.PHONY: ci-frontend
ci-frontend:
	$(MAKE) -C app ci

.PHONY: lint typecheck test migrate check-migrations test-cov coverage
lint typecheck test migrate check-migrations test-cov coverage:
	$(MAKE) -C api $@

.PHONY: fe-lint fe-typecheck fe-test
fe-lint:
	$(MAKE) -C app lint

.PHONY: fe-format-check
fe-format-check:
	$(MAKE) -C app format-check

fe-typecheck:
	$(MAKE) -C app typecheck

fe-test:
	$(MAKE) -C app test

.PHONY: e2e
e2e:
	$(MAKE) -C app e2e

.PHONY: sync sync-backend sync-frontend
sync: sync-backend sync-frontend
	@echo "✅ Dependencies synced (backend + frontend)"

sync-backend:
	$(MAKE) -C api sync

sync-frontend:
	$(MAKE) -C app sync
