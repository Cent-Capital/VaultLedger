# Phase 14 kickoff brief

Written 2026-08-05 at commit `05f4671`, clean tree, `make verify-track-a` exit 0
(135s, ruff clean, 111 passed, regression green).

This consolidates the actionable work found in the pre-Phase-14 review so a fresh
session does not have to re-derive priority from a 1600-line `PROGRESS.md`. It is
a task list, not a source of truth — `SPEC.md`, `PROGRESS.md`, and `decisions/`
remain authoritative, and this file should be deleted once Phase 14 closes.

## State

Phases 0–13 complete. Six ADRs. Track A shipped and demoed; portfolio expansion
six phases in. Read `SPEC.md` §0's **ACTIVE DEVIATIONS** banner first — seven
accepted deviations override parts of the spec body.

## 0. Blocking decision (owner, not an agent) — RESOLVED 2026-08-05

**ADR-0006 is `accepted`**, with one owner amendment: `AgentStep` gains an explicit
failure representation, because SPEC §8's five fields cannot record that a tool
raised and the ADR commits to hand-written partial-failure handling. That is a
SPEC §8 deviation and is now item 8 in the ACTIVE DEVIATIONS banner. The field
itself is **not yet implemented** — it lands with Phase 14's first commit.

## 1. Prerequisites — DONE 2026-08-05, no inference re-run

Both closed as reporting changes; see ADR-0006's *Prerequisites* section for what
each one now guarantees. Summary:

- **1a per-category metrics:** `category_metrics()` in `evals/matrix.py`, keyed
  `<metric>__<category>`, rendered as a per-category table by
  `write_matrix_report`. Denominators come from the golden set, so failed rows stay
  misses.
- **1b numeric exact-match:** **the metric was added; the AC was not restated.**
  `numeric_exact_match()` parses both sides and compares within
  `thresholds.numeric_epsilon`, so it is genuinely distinct from the literal-anchor
  `strict_answer_match`. Out-of-scope rows are held out of its denominator.
- **Reproducibility:** `python -m vaultledger.evals rescore` recomputes metrics
  from committed receipts through the *same* `score_answer()` the live matrix uses.
  Committed manifests were **not** rewritten. The baseline table lives in
  `reports/phase14_baseline_by_category.md`.
- `make lint` clean, `make test` 118 passed (was 111).

### Original text, kept for the record

Phase 14's AC is *"numeric exact-match on multi_hop/aggregation improves by a
stated, measured margin vs B."* Neither half is currently measurable.

**1a. Emit per-category metrics from the matrix.** Every manifest carries
aggregate `strict_answer_match_rate` only. The per-row `_answers.json` receipts
already carry `category`, `strict_match`, `citation_doc_hit`, and
`abstention_correct`, so this is a reporting change, not a re-run. Add
category-scoped metrics to `_cell_metrics` in `vaultledger/evals/matrix.py` and
surface them in `reports/model_matrix.md`.

*Why it matters beyond the AC:* aggregate-only metrics were the enabling condition
for issue 2 below. This is the fix that makes that class of error visible.

**1b. Define numeric exact-match, or restate the AC.** `strict_answer_match_rate`
is a literal-anchor scorer explicitly labelled a lower bound — not the numeric
exact-match SPEC names. Either add the metric or restate the AC against the scorer
that exists. **Say which was done**; do not let the two names blur.

**Baseline variant D must beat** (computed offline from the committed guards-on
receipts, n=80, failed rows scored as misses):

| category | n | `qwen3:4b` | `qwen3:8b` |
|---|---:|---:|---:|
| `aggregation` | 14 | 28.6% | 14.3% |
| `multi_hop` | 12 | 16.7% | **0.0%** |

8B answers **zero of twelve** multi-hop questions to strict match. If variant D
cannot beat that floor, publish the null result.

## 2. The router's category→tier map is backwards on 44 of 80 rows

Recorded as an amendment to `ADR-0004`. Measured on the exact guards-off receipts
the router eval consumed: 8B beats 4B on `single_doc` (66.7% vs 33.3%); 4B beats
8B on `aggregation` (28.6% vs 14.3%) and `multi_hop` (16.7% vs 0.0%). All three
route to the weaker model.

**Do not "fix" this by flipping the map.** Fitting the policy to the same 80 rows
that scored it repeats the circularity ADR-0004 already carries on its labels. The
correction is owed to Phase 17 on a held-out set, or must be stated openly as
fitted with its accuracy claim withdrawn.

## 3. Security work Phase 14 owes

The `sql` tool is the largest new attack surface in the project — SELECT-only with
a table allowlist, and SQL results carry `doc_id` provenance so citations survive
the tool hop, which means untrusted document text can influence a query path.

**Re-run Phase 7's injection suite with variant D live *and* Phase 13's guards
active.** The Phase 13 review proved the eval path can silently run with
`guardrail_toggles=None`, so passing that suite without the guards on would repeat
a known vacuous check. Pass `--guardrails on`.

## 4. Smaller issues, all recorded, none blocking

- **`OpenAICompatibleGenerator` is dead code** — no caller, no test. ADR-0003's
  amendment justified keeping `privacy.py` because tests exercise it; that does
  not extend to this class. Recommended for deletion. Owner's call.
- **`torchvision` absent while `transformers` expects it** on a lazy import path.
  Nothing broken. Same native stack as the unexplained signal-11 in Phase 10. If
  the segfault recurs, grab `~/Library/Logs/DiagnosticReports/` before restarting.
- **`golden_hash` covers the whole golden-set file**, so any metric-irrelevant edit
  trips the regression guard and forces a re-pin. Narrowing it needs its own ADR.
- **Which matrix arm is canonical** (`--guardrails off` vs `on`) is an open Phase
  17 decision. Default stays `off`.

## 5. Claims that must never be upgraded

These are load-bearing and have each already been caught drifting once:

- **Over-refusal:** report "0 of 6", never "≤5% achieved". Recorded *not
  meaningfully tested*. The ~60-row probe set (ADR-0005) does not exist.
- **Routing accuracy 100%:** *met in form only*. The labels are the policy
  serialised, and per issue 2 the policy is likely wrong.
- **Phase 13's injection AC:** verifies the wrapping of pre-existing guards only;
  the five new guards were inactive in that run.
- **Latency:** this harness cannot rank models by latency (~50% p50 movement on
  byte-identical answers). Both Phase 11's "4B is faster" and Phase 12's
  correction of it are withdrawn. ADR-0003 amendment 2.
- **Phase 6's "badge + `model_used` flip":** unit level only; not demonstrable in
  the product since the toggle was removed.
- **Cost:** `$0.00` means *unpriced, not free*.
- **Langfuse:** no span has ever reached a Langfuse project.

## 6. Outstanding Track-A documentation

- **Internship report draft** — belongs in `~/Desktop/PM-OS`, not this repo.
- **Demo re-record** — `demo/vaultledger_track_a_v1.gif` shows a privacy toggle
  the app no longer has. Flagged in `demo/README.md`; do not call it current.

## Working rules (from `CLAUDE.md`, non-negotiable)

- Never fabricate results. Eval numbers come from a real run with a `RunManifest`.
  If you did not run it, say "I have not tested this."
- Phase-gated: do not start a phase until the prior phase's ACs pass. Encode ACs
  as tests.
- Bounded loops only; budgets live in `config.yaml`. CI bans `while True`.
- Determinism: seed in `config.yaml`; the corpus regenerates byte-identical
  (re-verified 2026-08-05).
- Deviations from SPEC need an ADR, and the ADR must be added to SPEC §0's ACTIVE
  DEVIATIONS banner when accepted.
- Regenerate phase artifacts from a clean SHA before closing a phase; delete
  manifests whose `run_id` identifies no commit.
