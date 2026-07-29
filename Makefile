# VaultLedger developer entrypoints (SPEC.md Section 17).

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

.PHONY: install lint test data ingest eval-smoke eval-full matrix replay run clean

install:  ## Install the package + dev, synth, and Phase-4 reranking tools
	$(PYTHON) -m pip install -e ".[dev,synth,rerank]"
	$(PYTHON) -m spacy download en_core_web_sm

data:  ## Regenerate the synthetic corpus (byte-identical from the seed)
	$(PYTHON) -m vaultledger.synth

ingest:  ## Ingest the corpus: parse -> extract -> SQLite -> PII -> chunk -> index
	$(PYTHON) -m vaultledger.ingest

lint:  ## Static checks: ruff
	$(PYTHON) -m ruff check .

test:  ## Unit tests + schema/config/loop-lint gates
	$(PYTHON) -m pytest

eval-smoke:  ## Fast deterministic eval subset (Phase 3+)
	$(PYTHON) -m vaultledger.evals validate
	$(PYTHON) -m vaultledger.evals run --limit 12 --skip-if-unavailable

eval-safety:  ## Phase 7 live local-model gate (10 unanswerable + poisoned doc)
	$(PYTHON) -m vaultledger.evals safety

judge-validate:  ## Phase 9: validate judge against 20 human labels
	$(PYTHON) -m vaultledger.evals judge-validate

regression:  ## Phase 9: compare latest retrieval manifest with baseline
	$(PYTHON) -m vaultledger.evals regression

eval-full:  ## Full LLM evals, cost-capped (Phase 9+)
	$(PYTHON) -m vaultledger.evals validate
	$(PYTHON) -m vaultledger.evals safety
	$(PYTHON) -m vaultledger.evals judge-validate
	$(PYTHON) -m vaultledger.evals regression

matrix:  ## Multi-model benchmark matrix (Phase 11+)
	@echo "matrix: not implemented until Phase 11."

replay:  ## Re-execute a past query from its trace (Phase 8+)
	@echo "replay: not implemented until Phase 8. Usage: make replay TRACE=<trace_id>"

run:  ## Launch the Streamlit app
	$(PYTHON) -m streamlit run app/streamlit_app.py

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache *.egg-info build dist
