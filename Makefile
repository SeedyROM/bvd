.PHONY: help format lint lint-fix test test-cov test-cov-xml run

# Default target - show help
help: ## Show this help message
	@echo "BVD (Breaking Version Detector) - Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Examples:"
	@echo "  make help                       # Show this help message"
	@echo "  make build                      # Build the package"
	@echo "  make lint                       # Check code style and quality"
	@echo "  make format                     # Format all code"
	@echo "  make test                       # Run all tests"
	@echo "  make run -- --files example.tf  # Check specific file"
	@echo "  make run -- --help              # Show bvd help"

# Make help the default target
.DEFAULT_GOAL := help

format: ## Format code with black
	uv run black src/ tests/

lint: ## Check code style and quality with ruff
	uv run ruff check src/ tests/

lint-fix: ## Fix code style issues automatically
	uv run ruff check --fix src/ tests/

test: ## Run all tests with pytest
	uv run pytest tests/ $(filter-out $@,$(MAKECMDGOALS))

test-cov: ## Run tests with coverage report
	uv run pytest --cov=bvd --cov-report=term-missing --cov-report=html tests/ $(filter-out $@,$(MAKECMDGOALS))

test-cov-xml: ## Run tests with XML coverage report for CI
	uv run pytest --cov=bvd --cov-report=xml tests/ $(filter-out $@,$(MAKECMDGOALS))

run: ## Run bvd with arguments (e.g., make run -- --files example.tf)
	uv run bvd $(filter-out $@,$(MAKECMDGOALS))

build: ## Build the package
	uv build $(filter-out $@,$(MAKECMDGOALS))

# Catch-all target to prevent "No rule to make target" errors
%:
	@: