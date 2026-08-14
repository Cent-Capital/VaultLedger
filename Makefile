# VaultLedger developer entrypoints (SPEC.md Section 17).

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

.PHONY: install install-graph doctor lint test data ingest live-ingest watch eval-smoke eval-safety judge-validate regression eval-full verify-track-a matrix decoding-sweep decoding-proof decoding-parity-proof abstention-audit abstention-candidate support-coverage-replay variant-matrix failure-pareto adr-index router-eval guardrails-eval agentic-eval agentic-safety graph-index graph-eval graph-eval-k6 graph-vault graph-vault-extracted replay run clean

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
	$(PYTHON) -m vaultledger.evals run --variant A_naive
	$(PYTHON) -m vaultledger.evals run --variant B_hybrid
	$(PYTHON) -m vaultledger.evals regression

verify-track-a: lint test eval-full  ## Phase 10 acceptance gate

matrix:  ## Phase 18 canonical six-model B_hybrid bake-off
	$(PYTHON) -m vaultledger.evals matrix --limit 0 --guardrails on \
		--judge-model ollama/qwen3:8b --frontier reports/model_frontier.svg

decoding-sweep:  ## Phase 18 preregistered qwen3:8b temperature x top_p grid
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--decoding-sweep --limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/phase18_decoding_matrix.md \
		--frontier reports/phase18_decoding_frontier.svg

decoding-proof:  ## Phase 18: prove explicit defaults preserve output bytes
	$(PYTHON) -m scripts.phase18_decoding_proof

decoding-parity-proof:  ## Phase 18: prove product/eval chat paths match
	$(PYTHON) -m scripts.phase18_parity_proof

abstention-audit:  ## Phase 19: classify false-abstention causes and replay retrieval
	$(PYTHON) -m scripts.phase19_abstention_audit

abstention-candidate:  ## Phase 19: one evidence-first candidate cell vs the frozen baseline
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/phase19_candidate_matrix.md \
		--frontier reports/phase19_candidate_frontier.svg

support-coverage-replay:  ## ADR-0020: replay entity support over committed Phase 18 B_hybrid answers
	$(PYTHON) -m scripts.support_coverage_replay

variant-matrix:  ## Phase 19 A/B/C/D comparison from committed receipts, no inference
	$(PYTHON) -m vaultledger.evals variant-matrix

failure-pareto:  ## Phase 19 failure-taxonomy sequence, discovered by rule from receipts
	$(PYTHON) -m vaultledger.evals failure-pareto

adr-index:  ## Phase 19 decision index with outcome classes, generated from decisions/
	$(PYTHON) -m scripts.phase19_adr_index

router-eval:  ## Phase 12 routing accuracy + four-policy latency-quality frontier
	$(PYTHON) -m vaultledger.evals router-eval \
		--t0-answers reports/phase11_ollama_qwen3_4b_b_hybrid_61802221d874_answers.json \
		--t1-answers reports/phase11_ollama_qwen3_8b_b_hybrid_33c0a0d50c76_answers.json

guardrails-eval:  ## Phase 13 deterministic named-guard acceptance report
	$(PYTHON) -m vaultledger.evals guardrails-eval

agentic-eval:  ## Phase 14 full target-category matrix, guards on
	$(PYTHON) -m vaultledger.evals matrix --variants D_agentic --categories aggregation multi_hop --limit 0 --guardrails on --report reports/phase14_agentic_matrix.md

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
