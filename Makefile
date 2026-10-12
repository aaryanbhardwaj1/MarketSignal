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

.PHONY: worker
worker: ## Run the ingestion worker natively (Procrastinate)
	$(UV) run procrastinate --app=marketsignal.worker.app.app worker --queues=ingestion

.PHONY: seed
seed: ## Load the synthetic seed corpus through the real upload API (needs api + worker)
	$(UV) run python ../scripts/seed.py

.PHONY: seed-check
seed-check: ## Verify the seed corpus is byte-identical to its generator and self-consistent
	$(UV) run python ../seed_data/generator/verify.py

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

# ── offline demo (no live model: MS_LLM_ENABLED=false) ───────────────────────────────────────

.PHONY: demo
demo: ## Print the offline demo sequence
	@echo "Offline demo (no live model calls):"
	@echo "  1. make up            # postgres + redis"
	@echo "  2. make migrate       # schema"
	@echo "  3. make api-demo      # API on :8000 with MS_LLM_ENABLED=false MS_HIDE_TEST_WORKSPACES=true"
	@echo "  4. make worker        # ingestion worker (separate terminal)"
	@echo "  5. make seed          # synthetic corpus (fresh DB: make reset-db first)"
	@echo "  6. make demo-seed     # saved featured conversations from seed_data/demo"
	@echo "  7. pnpm --dir frontend dev   # web on :3000"
	@echo "  Pre-demo checks: make demo-verify; make demo-clean (dry run of test-workspace cleanup)"

.PHONY: api-demo
api-demo: ## Run the API on :8000 for the offline demo (live model off, test workspaces hidden)
	MS_LLM_ENABLED=false MS_HIDE_TEST_WORKSPACES=true $(UV) run uvicorn marketsignal.api.app:create_app --factory --port 8000

.PHONY: demo-export
demo-export: ## Re-export featured NORTHSTAR conversations to seed_data/demo (read-only)
	$(UV) run python ../scripts/demo_export.py

.PHONY: demo-seed
demo-seed: ## Import the demo snapshot after `make seed` (idempotent; aborts on corpus drift)
	$(UV) run python ../scripts/demo_import.py

.PHONY: demo-clean
demo-clean: ## Preview removal of test-harness workspaces; CONFIRM=yes deletes them
	$(UV) run python ../scripts/demo_reset.py --drop-test-workspaces $(if $(filter yes,$(CONFIRM)),--yes,--dry-run)

.PHONY: demo-verify
demo-verify: ## Re-verify curated insight numbers and citations against the corpus
	$(UV) run python ../scripts/verify_insights.py

.PHONY: eval-catalog
eval-catalog: ## Rebuild the evaluation catalog from committed eval artifacts
	$(UV) run python ../scripts/build_eval_catalog.py
