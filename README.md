# VaultLedger

Your private financial analyst that never phones home.

VaultLedger ingests financial documents (bank statements, 1099s, invoices, pay
stubs) entirely on your own machine, then answers natural-language questions
about them with citations back to the exact source. A visible **Privacy Switch**
lets you trade a little privacy for a little answer quality, and tells you every
time whether data left your machine. The centerpiece is a rigorous evals harness:
every retrieval, generation, routing, and guardrail decision is measured.

Synthetic data only. No real accounts, no bank linking, ever. Q&A and extraction,
never financial advice.

> Full design lives in [`SPEC.md`](./SPEC.md). Build progress and decisions live
> in [`PROGRESS.md`](./PROGRESS.md) and [`decisions/`](./decisions).

## Status

**Phases 0-9 complete** — scaffold/config, deterministic synthetic corpus,
ingestion/indexing, an 80-example golden set, measured naive-vs-hybrid
retrieval, and structured-output reliability. Phase 4 lifted recall@20 from
0.9587 to 0.9786 and MRR from 0.4974 to 0.7856
(`reports/phase4_comparison_latest.md`). Phase 5 added constrained JSON
generation, a bounded L1 repair loop, and snippet-verified citations with a
safe abstaining fallback — proven crash-free across a 100-query adversarial
suite (ADR-0002). Phase 6 added a consent-gated Local/Cloud switch, per-answer
egress badge, routing record, and visible local fallback when cloud is
unavailable. Phase 7 added prompt-injection isolation, lost-in-the-middle
context reordering, and a manifested live safety gate: all 10 unanswerable
golden questions abstained and the poisoned-document case answered normally
without dumping account numbers (`reports/phase7_latest.json`).
Phase 8 added durable six-stage local query traces, latency/token/health
telemetry, optional Langfuse export, and cost/latency rollups on the dashboard.
Phase 9 validated the versioned local LLM judge against 20 balanced human
labels (TPR/TNR both 1.00 on the clear calibration set) and added a
manifest-backed regression gate that catches threshold-breaking metric drops.
**Next: Phase 10** — Track-A polish and fresh-machine verification. See the
phase plan in SPEC.md Section 16 and the build log in PROGRESS.md.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) for local models (used from Phase 2 on)
- Cloud tiers (T2/T3) are optional; local mode needs no API keys

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
make install          # editable install + dev tools
make test             # unit tests and phase gates
make eval-smoke       # golden-set validation + small dense baseline if Ollama is running
make run              # launch the Streamlit app
```

Copy `.env.example` to `.env` only if you plan to use the cloud tiers.

## Layout

```
vaultledger/   the package (schemas, config, and per-phase modules)
app/           Streamlit UI (Library / Ask / Evals / Experiment Lab)
data/          synthetic PDFs + ground-truth records (generated)
reports/       harness-generated matrices, frontier chart, Pareto history
decisions/     Architecture Decision Records (ADRs)
tests/         pytest incl. spec-by-example
```

## Make targets

`make install · lint · test · data · ingest · eval-smoke · run` today.
`eval-full · matrix · replay` come online as their phases land.

## License

Proprietary — all rights reserved. See [`LICENSE`](./LICENSE). Created in
connection with an internship at Cent Capital LLC; not licensed for reuse.
