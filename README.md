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

**Phase 0 complete** — scaffold, typed config, data contracts, app shell.
Next: Phase 1 (synthetic data). See the phase plan in SPEC.md Section 16.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) for local models (used from Phase 2 on)
- Cloud tiers (T2/T3) are optional; local mode needs no API keys

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
make install          # editable install + dev tools
make test             # schemas import, config loads, loop-lint
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

`make install · lint · test · run` today. `eval-smoke · eval-full · matrix ·
replay` come online as their phases land.

## License

Proprietary — all rights reserved. See [`LICENSE`](./LICENSE). Created in
connection with an internship at Cent Capital LLC; not licensed for reuse.
