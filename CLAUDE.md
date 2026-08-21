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
deck, metric framing, design justifications, review passes) lives in an external
narrative workspace that is not distributed with this repository. Rough rule: if
the compiler or eval harness reads the output, it belongs here; if it is private
portfolio or internship narrative, it remains outside this public repository.

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
Phases 0–16 are closed. **Phase 17 is closed on a waiver (ADR-0013)** — say it that
way; "phases 0–17 closed" on its own overstates it. Its code half landed and is
verified (Gatekeeper instructions, first-run corpus bootstrap, cancellation/error
handling, service-first Ollama detection, regression/report corrections, the
context-budget fix and its lazy config resolution); 186 tests, lint, `make doctor`,
`make verify-track-a` and CI are all green.

Its **machine half was deferred in full, not met**: no fresh macOS
Administrator-account install has been run and `receipts/phase17_machine_half.md`
does not exist. Never describe the development-account or clean-virtualenv receipt as
that machine half, and never write "installs cleanly on a fresh Mac". Note ADR-0013
waives an *unattempted* gate, which is weaker than ADR-0010's waiver of a *measured
and missed* one. Owed before handoff: the fresh-account run and its receipt, checklist
items A5–A7, and an independent non-technical five-minute cold read — which no agent
and not the owner can substitute for.

**Phase 18 is closed.** Both preregistered experiments ran to completion and **both are
null**. ADR-0016: the six-model bake-off (2 families × 3 sizes, 80 rows each, 480 rows,
100% coverage, zero `TOOL_ERR`) found **no model that beat `qwen3:8b`** — exact McNemar
on paired judge verdicts put `gemma3:12b` at 6 wins / 4 losses (`p`=0.754) and
`qwen3:14b` at 3/8 (`p`=0.227), while `gemma3:4b`, `qwen3:4b` and `gemma3:1b` were
significantly worse. The two that tied cost 3.7–4.4× the median latency. ADR-0017: the
preregistered decoding sweep (6 profiles, 480 rows) found **no profile that beat
`0.0/0.95`**; all seven profiles pass exactly the same 35 strict rows despite 12% of
answers being reworded at temperature 0.7, and all 10 discordant judge rows favour the
baseline.

Say it as **"measured against five alternatives; none beat it"** — never "the best
available local model", which the data does not support. `p`=0.754 is absence of
evidence, not equivalence: ten discordant pairs give low power. The judge remains weak
evidence (its 20-label validation supports ≥83% accuracy; a null classifier scores
19/20), and `strict_answer_match` is confounded with verbosity — answer length and
strict rate rise together across all six models.

**The open lead is `FALSE_ABSTAIN`**: five of the ten rows separating the top two models,
plus `gs_005` in the sweep. Decoding moved zero rows and model choice moved two, so the
abstention policy — which fires whenever zero citations survive, on a verifier that only
confirms a snippet *exists* rather than *supports* — is the largest known remaining
lever. It needs its own phase, not a Phase 18 addendum.

**Phase 19 is open.** Its kickoff audit corrected the mechanism without changing the
finding: 15 of `qwen3:8b`'s 19 answerable abstentions were model-declared, three were
output-guard downgrades, and one was a deliberate query block. All 19 retrieval top
scores exceeded `rerank_tau`; expected documents were already in the top six for 14 and
the top 12 for 17. ADR-0018 preregistered one evidence-first prompt candidate. ADR-0019
rejects it: abstentions improved 19→15 and judge false-abstains 15→11, but paired judge
movement was only 2 wins / 0 losses (net +2, exact `p=0.500`) against the fixed +4 gate.
Three of four newly answered rows merely changed from `FALSE_ABSTAIN` to `INCORRECT`.
The original prompt is restored; no second candidate is allowed. ADR-0020 then
preregistered a support-aware entity-coverage citation guard. ADR-0021 rejects it before
any live cell: replay over 13 committed `B_hybrid` receipts / 1,040 rows predicted 96
downgrades, including 28 rows that already passed both judge and strict. Candidate
`gs_005` was caught, but the binding zero-false-positive gate failed. The unchanged
extractor remains replay-only and the product verifier is restored; do not tune it on
those rows or describe it as shipped. The inherited Phase 19 portfolio scope remains
owed.

Phase 16 (ADR-0011/ADR-0012) delivered the external
live-document path: inbox outside the repo, real OCR via `ocrmypdf --skip-text`,
provenance carried to the citation, incremental indexes and a bounded watcher. Its
scan arm was measured on a genuinely image-only PDF and passed — but that was one
cleanly rendered page, so **no OCR accuracy claim is made**. Phase 14 met its
Variant-D improvement AC on the shipped
8B model and regressed on 4B; the split result is recorded, not averaged away.
Phase 15 built Variant C but missed the preregistered entity-recall gate and
underperformed Variant B in an underpowered six-row global-summary comparison; B
is the provisional default. The preregistered equal-context arm was inconclusive
(C@6 landed exactly between B and C@12), so the run cannot separate graph retrieval
from context budget. ADR-0010 records the Phase-15-only failed-gate waiver. See the
latest `PROGRESS.md` entry and committed receipts for the exact boundaries.
