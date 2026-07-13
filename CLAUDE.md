# CLAUDE — VaultLedger

Privacy-first, local-first financial-document Q&A with a rigorous evals harness.
This is a portfolio + internship build (Cent Capital). The point is not just a
working RAG app — it's to surface AI-PM competencies (evals, RAG variants, model
routing, guardrails, observability, cost attribution) and to be honest about
what's actually been measured.

## Read these first, every session
- `SPEC.md` — the master build spec (PRD + engineering spec + experiment plan +
  phased build plan). It is the source of truth. Do not drift from it without an
  ADR in `decisions/`.
- `PROGRESS.md` — the honest build log. One entry per phase: what got built, what
  deviated from SPEC and why, and a plain-English explainer of the trickiest
  piece. **Append to it as you finish a phase. No backdating, no compressing —
  the commit history is the receipt.**

## Reasoning core (inherited, global)
The global `~/.claude/CLAUDE.md` reasoning/honesty rulebook applies here and
governs. Load `/reasoning-operating-system` for any non-trivial analysis. The
non-negotiables that bite hardest on this repo:
- **Never fabricate results.** Say "I have not tested this" / "reasoned estimate,
  not a measured result" when that's the truth. Eval numbers must come from a
  real run with a `RunManifest`, never invented or hand-waved.
- **Verify before claiming.** Re-derive material numbers; check that a metric's
  numerator/denominator/population/period are defined and attached to a decision.
- **Label uncertainty at the point it appears**, not in a closing disclaimer.

## Product/narrative work lives elsewhere
Code, tests, evals, ADRs → here. The *story* around it (PRD, internship report,
deck, metric framing, design justifications, review passes) → the PM-OS
workspace at `~/Desktop/PM-OS` and its skills (`/pm-operating-system`,
`/experiment-metrics`, `/decision-doc`, `/prd-review-panel`, `/ralph-wiggum`).
Rough rule: if the compiler or eval harness reads the output, it's here; if a
recruiter or the Cent Capital lead reads it, it's PM-OS.

## Build discipline
- **Phase-gated.** Don't start a phase until the prior phase's acceptance
  criteria (SPEC §16) pass. Encode ACs as tests.
- **Daily commits**, honest messages. Commit identity is set to no-reply.
- **Determinism.** Seed is in `config.yaml`. The synthetic corpus regenerates
  byte-identical from the seed (`make data` / `python -m vaultledger.synth`).
- **Bounded loops only** (SPEC §15.2 — CI bans `while True`). Every loop has a
  budget in `config.yaml`.
- **Config is typed.** Every knob routes through `vaultledger/config.py` over
  `config.yaml`; a bad config fails loud at startup.

## Layout
- `vaultledger/` — package: `synth/ ingest/ index/ retrieve/ route/ gateway/
  guardrails/ generate/ observability/ evals/`, plus `schemas.py` (Section 8
  contracts) and `config.py`.
- `data/synthetic_pdfs/` (gitignored, regenerable) · `data/ground_truth/`
  (committed: per-doc records + `entities.json`).
- `decisions/` — ADRs (Appendix A template). `reports/` — harness-generated.
- `app/streamlit_app.py` — Library / Ask / Evals / Experiment Lab.
- `tests/` — pytest incl. spec-by-example (SPEC §18).

## Commands
- `make install` — editable install with `[dev,synth]`.
- `make data` — regenerate the synthetic corpus.
- `make test` / `make lint` — pytest + ruff (the CI gate).
- `make run` — launch the Streamlit app.

## Status
Phase 0 (scaffold) and Phase 1 (synthetic data) complete. **Next: Phase 2 —
ingestion & indexing.** See `PROGRESS.md` for details.
