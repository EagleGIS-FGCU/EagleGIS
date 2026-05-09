# Makefile — ergonomic command center for the EagleGIS pipeline.
# All targets work from the repo root. Run `make help` for a menu.

.PHONY: help install install-dev test build publish publish-dry verify check \
        run-server clean clean-runs hooks ci

PYTHON ?= python3
VENV   ?= .venv

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:  ## Show this menu
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	      /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

install:  ## Create venv (if missing) and install runtime deps
	@if [ ! -d $(VENV) ]; then $(PYTHON) -m venv $(VENV); fi
	@$(VENV)/bin/pip install --upgrade pip > /dev/null
	@$(VENV)/bin/pip install -r requirements.txt
	@echo "Installed. Activate with: source $(VENV)/bin/activate"

install-dev: install  ## Install dev deps (pre-commit) and register hooks
	@$(VENV)/bin/pip install pre-commit
	@$(VENV)/bin/pre-commit install
	@echo "Pre-commit hooks installed."

hooks: install-dev  ## Alias for install-dev

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

build:  ## Build silver from bronze (offline, no Supabase)
	@$(VENV)/bin/python -m app.pipeline.run

publish:  ## Build silver and upsert to Supabase, then verify (needs SUPABASE_*)
	@$(VENV)/bin/python -m app.pipeline.run --publish --verify

publish-dry:  ## Show what would be upserted without making remote calls
	@$(VENV)/bin/python -m app.pipeline.run --publish --dry-run

verify:  ## Diff Supabase against silver (read-only)
	@$(VENV)/bin/python -m app.pipeline.run --verify

check:  ## Build silver in --strict mode (fail on rejects); used by CI
	@$(VENV)/bin/python -m app.pipeline.run --strict

# ---------------------------------------------------------------------------
# Tests + serve
# ---------------------------------------------------------------------------

test:  ## Run the test suite
	@$(VENV)/bin/pytest -q

run-server:  ## Run the FastAPI app locally on :8000 (needs SUPABASE_*)
	@$(VENV)/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

ci: check test  ## What CI runs: strict pipeline + tests
	@echo "ci ok"

clean-runs:  ## Remove generated run manifests
	@rm -rf app/data/runs/

clean: clean-runs  ## Remove venv, caches, and runtime artifacts
	@rm -rf $(VENV) **/__pycache__ .pytest_cache app/pipeline/__pycache__ \
	        app/pipeline/*/__pycache__ tests/__pycache__
