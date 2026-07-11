# VaultLedger developer entrypoints (SPEC.md Section 17).
# Eval targets are stubbed until Phase 3 stands up the harness.

.PHONY: install lint test eval-smoke eval-full matrix replay run clean

install:  ## Install the package + dev tools into the active environment
	python -m pip install -e ".[dev]"

lint:  ## Static checks: ruff
	ruff check .

test:  ## Unit tests + schema/config/loop-lint gates
	pytest

eval-smoke:  ## Fast deterministic eval subset (Phase 3+)
	@echo "eval-smoke: not implemented until Phase 3 (golden set + retrieval metrics)."

eval-full:  ## Full LLM evals, cost-capped (Phase 9+)
	@echo "eval-full: not implemented until Phase 9."

matrix:  ## Multi-model benchmark matrix (Phase 11+)
	@echo "matrix: not implemented until Phase 11."

replay:  ## Re-execute a past query from its trace (Phase 8+)
	@echo "replay: not implemented until Phase 8. Usage: make replay TRACE=<trace_id>"

run:  ## Launch the Streamlit app
	streamlit run app/streamlit_app.py

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache *.egg-info build dist
