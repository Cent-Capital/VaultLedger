# VaultLedger developer entrypoints (SPEC.md Section 17).

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

.PHONY: install install-graph doctor lint test data ingest live-ingest watch eval-smoke eval-safety judge-validate regression eval-full verify-track-a matrix router-eval guardrails-eval agentic-eval agentic-safety graph-index graph-eval graph-eval-k6 graph-vault graph-vault-extracted replay run clean

install:  ## Install the package + dev, synth, reranking, and model gateway tools
	$(PYTHON) -m pip install -e ".[dev,synth,rerank,gateway,graph]"
	$(PYTHON) -m spacy download en_core_web_sm

install-graph:  ## Install Phase 15's isolated LightRAG + NetworkX dependencies
	$(PYTHON) -m pip install -e ".[graph]"

doctor:  ## Read-only check of the documented local Track-A setup
	$(PYTHON) -m vaultledger.doctor

data:  ## Regenerate the synthetic corpus (byte-identical from the seed)
	$(PYTHON) -m vaultledger.synth

ingest:  ## Ingest the corpus: parse -> extract -> SQLite -> PII -> chunk -> index
	$(PYTHON) -m vaultledger.ingest

live-ingest:  ## Scan the external live inbox once after the file-stability gate
	$(PYTHON) -m vaultledger.ingest --live-once

watch:  ## Watch the external live inbox for the configured bounded poll budget
	$(PYTHON) -m vaultledger.ingest --watch

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
	$(PYTHON) -m vaultledger.evals guardrails-eval
	$(PYTHON) -m vaultledger.evals judge-validate
	$(PYTHON) -m vaultledger.evals regression

verify-track-a: lint test eval-full  ## Phase 10 acceptance gate

matrix:  ## Multi-model benchmark matrix (Phase 11+)
	$(PYTHON) -m vaultledger.evals matrix

router-eval:  ## Phase 12 routing accuracy + four-policy latency-quality frontier
	$(PYTHON) -m vaultledger.evals router-eval

guardrails-eval:  ## Phase 13 deterministic named-guard acceptance report
	$(PYTHON) -m vaultledger.evals guardrails-eval

agentic-eval:  ## Phase 14 full target-category matrix, guards on
	$(PYTHON) -m vaultledger.evals matrix --variants D_agentic --categories aggregation multi_hop --limit 0 --guardrails on

agentic-safety:  ## Phase 14 live Phase-7 suite rerun, Variant D + guards on
	$(PYTHON) -m vaultledger.evals safety --variant D_agentic --guardrails on

graph-vault:  ## Phase 15 demo-only ground-truth vault (not extraction evidence)
	$(PYTHON) -m vaultledger.graph export-ground-truth --replace

graph-vault-extracted:  ## Phase 15 extracted LightRAG graph projection
	$(PYTHON) -m vaultledger.graph export-extracted --replace

graph-index:  ## Phase 15 full LightRAG index + local-compute receipt
	$(PYTHON) -m vaultledger.graph build

graph-eval:  ## Phase 15 same-model B-vs-C comparison on all global-summary rows
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b --variants B_hybrid C_graph --categories global_summary --limit 0 --guardrails on --out-dir reports --report reports/phase15_global_summary_matrix.md

graph-eval-k6:  ## Pre-registered Phase 15 C_graph context-budget sensitivity arm
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b --variants C_graph --categories global_summary --limit 0 --guardrails on --graph-answer-top-n 6 --out-dir reports --report reports/phase15_graph_k6_matrix.md

replay:  ## Not built: Phase 8 declined raw-input replay on privacy grounds
	@echo "replay: deliberately NOT built. Phase 8 declined it because persisting raw"
	@echo "financial questions and retrieved context would broaden local data retention,"
	@echo "which contradicts the product thesis. Trace metadata is retained; raw-input"
	@echo "replay is not claimed. See PROGRESS.md Phase 8 and SPEC deviation 6."
	@exit 1

run:  ## Launch the Streamlit app without telemetry or first-run prompts
	$(PYTHON) -m streamlit run app/streamlit_app.py --server.headless=true --server.address=127.0.0.1 --server.fileWatcherType=none --browser.gatherUsageStats=false

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache *.egg-info build dist
