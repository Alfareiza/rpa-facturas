# Ensure we use bash for better portability of checks
SHELL := /bin/bash

# Main script (module path for python -m)
MAIN := src.main

.PHONY: run deploy venv

# Default target
all: run

# Create virtual environment with python3.10
venv:
	@command -v python3.10 >/dev/null 2>&1 || (echo "Error: python3.10 not found."; exit 1)
	python3.10 -m venv .venv

# Run the main script: uses venv (creates/activates if needed), python3, logs to project root
run:
	@pgrep -f "$(MAIN)" >/dev/null 2>&1 && { echo "Error: script is already running."; exit 1; } || true
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		[ -d .venv ] || $(MAKE) venv; \
		source .venv/bin/activate && python3 -m $(MAIN) 2>&1 | tee -a run.log; \
	else \
		command -v python3 >/dev/null 2>&1 || (echo "Error: python3 not found."; exit 1); \
		python3 -m $(MAIN) 2>&1 | tee -a run.log; \
	fi

# Deploy: pull latest code
deploy:
	git pull
