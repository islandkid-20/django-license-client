# django-license-client Makefile
#
# This package ships inside every product you deploy to a customer. There is no
# Django project here to run - only the library, its tests, and the formatters.

.PHONY: help install test clean format lint pre-commit pre-commit-update \
        pre-commit-run build check-sync

PYTHON ?= $(shell [ -x venv/bin/python ] && echo venv/bin/python || echo python3)
PIP    := $(PYTHON) -m pip

# Kept identical to license-server/Makefile.
FMT_EXCLUDE_DIRS  = venv,env,build,dist
FMT_EXCLUDE_REGEX = venv|env|build|dist

help:
	@echo "Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    install       - Install the package and dev dependencies (editable)"
	@echo "    build         - Build the wheel and sdist"
	@echo ""
	@echo "  Testing & Quality:"
	@echo "    test          - Run the enforcement tests"
	@echo "    format        - Format code (autoflake, isort, black, ruff)"
	@echo "    lint          - Run linter (ruff)"
	@echo "    pre-commit    - Install the pre-commit git hook"
	@echo "    pre-commit-run    - Run all hooks against every file"
	@echo "    pre-commit-update - Bump hook revs (then re-pin pyproject.toml)"
	@echo "    check-sync    - Verify signing.py matches the licence server's copy"
	@echo ""
	@echo "  Utilities:"
	@echo "    clean         - Clean up cache, build and temp files"

install:
	$(PIP) install -e ".[dev]"
	make pre-commit

build:
	$(PYTHON) -m build

test:
	$(PYTHON) -m pytest

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .ruff_cache .pytest_cache build dist *.egg-info

format:
	$(PYTHON) -m autoflake --in-place --remove-unused-variables --remove-all-unused-imports \
		-r . --exclude $(FMT_EXCLUDE_DIRS)
	$(PYTHON) -m isort . --profile black --skip venv --skip env
	$(PYTHON) -m black . --exclude '$(FMT_EXCLUDE_REGEX)'
	$(PYTHON) -m ruff check --fix .

# Exclusions live in ruff.toml - passing --exclude here would override them.
lint:
	$(PYTHON) -m ruff check .

# Install only. Hook revs are pinned to match pyproject's [dev] extra; autoupdate is a
# separate, deliberate step so `make install` cannot silently drift them apart.
pre-commit:
	$(PYTHON) -m pre_commit install

pre-commit-update:
	$(PYTHON) -m pre_commit autoupdate
	@echo
	@echo "Revs bumped. Update the matching pins in pyproject.toml before committing."

pre-commit-run:
	$(PYTHON) -m pre_commit run --all-files

# The token key derivation must be byte-identical on both sides or every deployed
# instance fails to verify its token. Cheap to check, catastrophic to get wrong.
SERVER_SIGNING = ../license-server/apps/licensing/signing.py
# One shell block, POSIX sh only: make does not run bash, so no process substitution.
SIGN_GREP = grep -E 'TOKEN_KEY_LABEL|hmac.new'
check-sync:
	@if [ ! -f $(SERVER_SIGNING) ]; then \
		echo "skip: $(SERVER_SIGNING) not present"; \
	elif [ "$$($(SIGN_GREP) license_client/signing.py)" = "$$($(SIGN_GREP) $(SERVER_SIGNING))" ]; then \
		echo "ok: token key derivation matches the licence server"; \
	else \
		echo "MISMATCH: license_client/signing.py has diverged from the server."; \
		echo "Every deployed instance will fail to verify its token."; \
		exit 1; \
	fi
