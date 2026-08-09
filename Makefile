# One command vocabulary, shared with lm-dashboard. Run `make` or `make help`
# to list targets. This is a thin wrapper over scripts/ and the compose files,
# so behavior matches running those by hand.
#
# Docker targets honor COMPOSE, so on a host where docker needs sudo run e.g.
#   make dev COMPOSE='sudo docker compose'
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help install dev down logs ps test lint format format-check build deploy

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the backend (editable, dev extras) and client deps
	cd server && pip install -e '.[dev]'
	npm --prefix client install

dev: ## Start the local dev stack (api reload + Vite on :5173); Ctrl-C to stop
	$(COMPOSE) up

down: ## Stop the local dev stack
	$(COMPOSE) down

logs: ## Follow the stack logs
	$(COMPOSE) logs -f

ps: ## Show stack status
	$(COMPOSE) ps

test: ## Run backend (pytest) and client (vitest) tests
	cd server && pytest -q
	npm --prefix client test

lint: ## Lint the backend with ruff
	cd server && ruff check vex_agent tests

format: ## Format the backend (ruff) and client (prettier)
	cd server && ruff format vex_agent tests
	npm --prefix client run format

format-check: ## Check formatting without writing changes
	cd server && ruff format --check vex_agent tests
	npm --prefix client run format:check

build: ## Build the client into client/dist (nginx serves this in prod)
	npm --prefix client run build

deploy: ## Prod deploy: roll the stack + migrations, then rebuild the client
	./scripts/deploy.sh
	npm --prefix client run build
