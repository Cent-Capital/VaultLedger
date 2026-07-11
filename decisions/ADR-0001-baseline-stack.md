# ADR-0001: Phase 0 baseline stack

Date: 2026-07-11 · Status: accepted

## Context
Phase 0 needs a language, a UI surface, a data-contract library, and a config
mechanism before any feature code exists. These choices are load-bearing (they
shape every later phase) but should follow the SPEC's decisive defaults rather
than reopen settled questions. This ADR records the baseline so later ADRs can
reference and, where warranted, supersede it.

## Options
- **Python 3.11 + Streamlit + Pydantic v2 + pydantic-settings (SPEC 7.1).**
  Fastest path to a demoable app; Pydantic gives runtime-validated contracts
  that double as the structured-output layer later; pydantic-settings gives one
  typed config object. Matches the spec's stated defaults.
- **FastAPI + a JS frontend.** More production-shaped and flexible UI, but
  multiplies surface area and slows the solo build; the UI is a harness
  front-end, not the deliverable — the deliverable is the evals.
- **Notebook-driven (Jupyter).** Fast to prototype, poor for a shippable app,
  a testable package, or a clean repo a recruiter reads.

## Decision
Take the SPEC 7.1 defaults: Python 3.11, Streamlit for the UI, Pydantic v2 for
all data contracts, `pydantic-settings` reading a single `config.yaml`. Package
laid out per SPEC Section 17. Ruff for lint, pytest for tests, GitHub Actions
for CI (including a `while True` lint that encodes the SPEC 15.2 bounded-loop
rule from day one).

## Consequences
- Easier: one validated `Answer`/`Config` object flows through the whole system;
  the same Pydantic models power structured-output repair (Phase 5) and eval
  scoring for free. Streamlit gets all four screens demoable quickly.
- Harder: Streamlit's rerun model will need care once state and long-running
  eval jobs appear; revisit if the UI fights us. Not a production web stack —
  acceptable, since "runs locally" is an explicit non-goal boundary.
- Revisit: vector store, embeddings, model gateway, graph engine, and eval
  framework each get their own ADR at the phase that introduces them.

## Evidence
None yet (baseline). First measurements arrive with the Phase 3 golden-set
RunManifest.
