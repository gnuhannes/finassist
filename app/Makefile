.PHONY: help
help:
	@echo "Targets (app):"
	@echo "  make ci         - lint + typecheck (+ test if present)"
	@echo "  make lint       - ESLint"
	@echo "  make format     - Prettier (write)"
	@echo "  make format-check - Prettier (check)"
	@echo "  make typecheck  - TypeScript typecheck"
	@echo "  make test       - Frontend tests (if configured)"
	@echo "  make e2e        - Playwright E2E (boots api + app; not part of ci)"
	@echo "  make sync       - Install dependencies"
	@echo "  make run        - Run dev server"


.PHONY: lint
lint:
	pnpm run lint

.PHONY: format
format:
	pnpm run format

.PHONY: format-check
format-check:
	pnpm run format:check

.PHONY: typecheck
typecheck:
	pnpm run typecheck

.PHONY: test
test:
	pnpm run -s test

.PHONY: ci
ci: lint typecheck format-check test
	@echo "✅ app checks passed"

# E2E is deliberately not part of `ci` — it is heavier (boots the backend +
# frontend, needs a browser) and runs as its own CI job. See docs/adr/0005.
.PHONY: e2e
e2e:
	pnpm run e2e

.PHONY: sync
sync:
	pnpm install --frozen-lockfile

.PHONY: run
run:
	pnpm dev
