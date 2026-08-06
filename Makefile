# Mytheca — research-record targets.
#
# This Makefile exists for docs/research/ tooling only. It does NOT replace app.py,
# which owns Docker and both dev servers:
#
#   uv run python app.py            # backend + frontend
#   uv run python app.py backend    # one side
#   uv run python app.py stop       # stop both
#
# Contract: docs/research/AGENT_INSTRUCTIONS.md

PY := uv run python

.DEFAULT_GOAL := help
.PHONY: help new-experiment validate-research research-index figures test

help:  ## Show this help
	@echo "Mytheca research-record targets:"
	@echo
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Run the app with 'uv run python app.py', not make."

new-experiment:  ## Scaffold an experiment. Usage: make new-experiment SLUG=my-slug
ifndef SLUG
	$(error SLUG is required — usage: make new-experiment SLUG=my-slug)
endif
	@$(PY) -m utils.scripts.research.new_experiment $(SLUG) $(if $(TITLE),--title "$(TITLE)",)

validate-research:  ## Enforce the research-record contract; non-zero exit on any violation
	@$(PY) -m utils.scripts.research.validate_research

research-index:  ## Regenerate docs/research/INDEX.md from every manifest
	@$(PY) -m utils.scripts.research.gen_index

figures:  ## Regenerate every experiment's figures from its recorded metrics
	@set -e; \
	found=0; \
	for gen in docs/research/experiments/*/figures/make_figures.py; do \
		[ -e "$$gen" ] || continue; \
		found=1; \
		echo "regenerating $$gen"; \
		$(PY) "$$gen"; \
	done; \
	for gen in docs/research/figures/sources/make_*.py; do \
		[ -e "$$gen" ] || continue; \
		found=1; \
		echo "regenerating $$gen"; \
		$(PY) "$$gen"; \
	done; \
	if [ "$$found" = "0" ]; then echo "no figure generators found (nothing promoted yet)"; fi

test:  ## Run the research tooling tests only
	@uv run pytest utils/tests/tools -q
