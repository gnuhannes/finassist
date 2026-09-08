DB_URL ?= sqlite+aiosqlite:///./data/my_private_finances.sqlite
ACCOUNT_ID ?= 1
CSV ?=
DELIMITER ?= ,
DATE_FORMAT ?= iso
DECIMAL_COMMA ?=

.PHONY: help
help:
	@echo "Targets (api):"
	@echo "  make ci               - ruff + mypy + pytest (coverage gate) + migration drift check"
	@echo "  make lint             - Ruff check + format check"
	@echo "  make lint-fix          - Ruff auto-fix + format"
	@echo "  make typecheck        - Mypy"
	@echo "  make test             - Pytest"
	@echo "  make test-cov          - Pytest with coverage report (no gate)"
	@echo "  make coverage          - Pytest with coverage gate (MIN_COVERAGE)"
	@echo "  make migrate          - Alembic upgrade head"
	@echo "  make check-migrations - Detect schema drift via autogenerate"
	@echo "  make sync              - Install dependencies"
	@echo "  make run               - Start backend application"

.PHONY: lint
lint:
	poetry run ruff check .
	poetry run ruff format --check .

.PHONY: lint-fix
lint-fix:
	poetry run ruff check . --fix
	poetry run ruff format .

.PHONY: typecheck
typecheck:
	poetry run mypy my_private_finances

.PHONY: test
test:
	poetry run pytest

.PHONY: test-cov
test-cov:
	poetry run pytest --cov=my_private_finances --cov-report=term-missing

# CI/Gate: fail under MIN_COVERAGE.
# Ratchet only upward toward the 80% target (ECC standard). Never lower it.
MIN_COVERAGE ?= 76

.PHONY: coverage
coverage:
	poetry run pytest --cov=my_private_finances --cov-fail-under=$(MIN_COVERAGE) --cov-report=term-missing

.PHONY: migrate
migrate:
	poetry run alembic upgrade head

.PHONY: check-migrations
check-migrations:
	@# Ensure the target DB is at head so autogenerate can diff metadata vs database
	@poetry run alembic upgrade head >/dev/null

	@rm -f alembic/versions/__ci_check__*.py
	@poetry run alembic revision --autogenerate -m "__ci_check__" --rev-id __ci_check__ >/dev/null || { \
		echo "❌ Alembic autogenerate failed. Is the database up to date?"; \
		exit 1; \
	}

	@f=$$(ls alembic/versions/__ci_check__*.py 2>/dev/null | head -n 1); \
	if [ -z "$$f" ]; then \
		echo "✅ No schema drift (no file generated)."; \
		exit 0; \
	fi; \
	if grep -Eq "op\.(create_table|drop_table|add_column|drop_column|alter_column|create_index|drop_index|create_unique_constraint|drop_constraint|execute)\b" "$$f"; then \
		echo "❌ Schema drift detected (autogenerate has operations)."; \
		echo "   Please create and commit a real migration."; \
		echo ""; \
		sed -n '1,220p' "$$f"; \
		rm -f "$$f"; \
		exit 1; \
	else \
		echo "✅ No schema drift (autogenerate produced empty migration)."; \
		rm -f "$$f"; \
	fi

.PHONY: ci
ci: lint typecheck coverage check-migrations
	@echo "✅ api checks passed"

.PHONY: sync
sync:
	poetry install --no-interaction --sync

.PHONY: run
run:
	poetry run uvicorn my_private_finances.main:app --reload --port 5179

import-csv:
	poetry run python -m my_private_finances.cli.import_csv \
		--db $(DB_URL) \
		--account-id $(ACCOUNT_ID) \
		--delimiter "$(DELIMITER)" \
		--date-format $(DATE_FORMAT) \
		$(if $(DECIMAL_COMMA),--decimal-comma,) \
		$(CSV)


