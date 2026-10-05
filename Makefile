# MarketSignal developer commands. `make help` lists targets.
# Light mode: postgres + redis in containers; API / worker / web run natively.

SHELL := /bin/bash
BACKEND := backend
UV := uv --directory $(BACKEND)

.DEFAULT_GOAL := help

.PHONY: help
help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env

.PHONY: env
env: .env ## Create .env from .env.example (dev-only placeholders)

.PHONY: up
up: .env ## Start postgres + redis (light mode) and wait until healthy
	docker compose up -d --wait postgres redis

.PHONY: up-full
up-full: .env ## Start everything in containers (migrate + api)
	docker compose --profile full up -d --build --wait

.PHONY: down
down: ## Stop containers (data volume kept)
	docker compose --profile full down

.PHONY: reset-db
reset-db: ## Destroy the local database volume and recreate it (DESTRUCTIVE, local only)
	docker compose --profile full down -v
	docker compose up -d --wait postgres redis

.PHONY: sync
sync: ## Install backend dependencies (uv, Python 3.13)
	$(UV) sync

.PHONY: migrate
migrate: ## Apply migrations as the schema-owner role
	$(UV) run alembic upgrade head

.PHONY: api
api: ## Run the API natively with reload on :8000
	$(UV) run uvicorn marketsignal.api.app:create_app --factory --reload --port 8000

.PHONY: lint
lint: ## Ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

.PHONY: fmt
fmt: ## Ruff autofix + format
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

.PHONY: typecheck
typecheck: ## mypy (strict)
	$(UV) run mypy

.PHONY: test-unit
test-unit: ## Unit tests (no services needed)
	$(UV) run pytest -m "not integration"

.PHONY: test-integration
test-integration: ## Integration tests (needs `make up` + `make migrate`)
	$(UV) run pytest -m integration

.PHONY: test
test: test-unit test-integration ## All backend tests

.PHONY: safety
safety: ## Public-repository safety check over tracked files
	scripts/check_repo_safety.sh --tracked

.PHONY: check
check: safety lint typecheck test ## Everything CI runs for the backend
