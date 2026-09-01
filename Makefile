# Four commands, so nothing depends on remembering a flag.
#
#   make setup     one-time: virtualenv, dependencies, the NER model
#   make test      the guarantees in the README, as tests
#   make briefs    regenerate the example briefs from live public sources
#   make doctor ORG="…"   why a brief came back empty

AS_OF ?= 2026-08-31
PY    := .venv/bin/python
PIP   := .venv/bin/pip
BIN   := .venv/bin/prebrief

.PHONY: setup test briefs doctor fresh clean

setup:
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e . pytest
	$(PY) -m spacy download en_core_web_sm
	@echo "\nready — now: make test"

test:
	$(PY) -m pytest -q

# Regenerates from cache where it exists. Use `make fresh` after changing how a
# source builds its query, or the old failed responses will be replayed.
briefs:
	$(BIN) run --batch examples/orgs.txt --as-of $(AS_OF)

fresh:
	rm -rf cache briefs
	$(BIN) run --batch examples/orgs.txt --as-of $(AS_OF)

doctor:
	$(BIN) doctor "$(ORG)" --as-of $(AS_OF)

clean:
	rm -rf .venv .pytest_cache **/__pycache__ *.egg-info src/*.egg-info
