.PHONY: help serve build update clean lint format-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

serve: ## Start local Zensical dev server
	zensical serve

build: ## Build the Zensical site
	zensical build --clean

update: ## Regenerate plugin docs (PLUGINS.md, docs/plugins/*, docs/install/*)
	python3 scripts/scan_deps.py
	python3 scripts/generate_plugin_docs.py

clean: ## Remove build artifacts
	rm -rf site/ docs/plugins.md docs/plugins/ docs/install/

lint: ## Run ruff linter on plugins
	ruff check plugins/

format-check: ## Check ruff formatting on plugins
	ruff format --check plugins/
