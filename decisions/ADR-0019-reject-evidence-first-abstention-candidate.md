# ADR-0019: Reject the evidence-first abstention candidate

2026-08-14 · Status: **accepted** · Applies ADR-0018's preregistered rule

## Context

ADR-0018 allowed one prompt candidate after Phase 19's causal audit found that 15 of
`qwen3:8b`'s 19 answerable abstentions were model-declared. The candidate added the exact
evidence-first instruction committed in ADR-0018 and changed no retrieval, guard,
decoding, context, or loop control. Commit `a37b5bf` recorded the candidate prompt as
SHA-256 `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c`
in the checkpoint, manifest, and generated report before the cell ran.

One full `ollama/qwen3:8b` / `B_hybrid` / guardrails-on cell completed all 80 golden
rows with a fixed `qwen3:8b` judge. Its comparator is the frozen Phase 18 baseline; the
model, variant, config hash, golden-set hash, seed, decoding profile, context width, and
guard arm match. The prompt is the only answer-affecting difference.

| Metric | Frozen baseline | Candidate | Change |
|---|---:|---:|---:|
| Answerable abstentions | 19/70 | 15/70 | -4 |
| Judge `FALSE_ABSTAIN` | 15/80 | 11/80 | -4 |
| Judge passes | 56/80 | 58/80 | +2 |
| Strict matches | 35/80 | 36/80 | +1 |
| Citation-document hits | 57/80 | 60/80 | +3 |
| Correct abstention decisions | 61/80 | 65/80 | +4 |
| Numeric exact matches | 15/42 | 15/42 | 0 |
| Generation / judge coverage | 80/80 | 80/80 | 0 |
| `TOOL_ERR` | 0 | 0 | 0 |

The aggregate movement hides the decision-relevant row behavior. Four rows stopped
abstaining: `mh_002`, `mh_008`, `mh_009`, and `gs_005`. Only `mh_002` became judge-
correct. `mh_008` and `mh_009` answered the comparison in the wrong direction;
`gs_005` added a merchant absent from its supporting evidence. The judge failure label
therefore moved from `FALSE_ABSTAIN` to `INCORRECT` on three rows without moving those
rows from failure to success.

Paired judge verdicts moved on only two rows: candidate wins on `mh_002` and `gb_004`,
with zero losses. Exact two-sided McNemar on 2 wins / 0 losses gives `p = 0.500`. This is
low-power evidence, not equivalence, but ADR-0018's adoption threshold was practical and
explicit: at least four more wins than losses. The observed net is +2.

## Options

**Adopt because the aggregate abstention thresholds passed.** Rejected. It would ignore
the conjunctive rule and count three false-abstention-to-incorrect conversions as product
improvements. The rule required both fewer abstentions and at least four paired net judge
wins precisely to prevent that interpretation.

**Tune a second evidence-first prompt.** Prohibited by ADR-0018. The same 80 rows have
now influenced the hypothesis, the candidate, and the decision. Iterating after seeing
which three rows became incorrect would be golden-set fitting, not a preregistered test.

**Reject the candidate and restore the shipped prompt.** Chosen. Keep the experiment and
the prompt-identity plumbing as evidence; remove only the evidence-first block from the
product path.

## Decision

**Reject the evidence-first candidate.** ADR-0018 condition 2 failed: paired judge
verdicts were 2 wins / 0 losses, net +2 rather than the required +4. The exact McNemar
`p = 0.500` is reported separately and is not being substituted for the preregistered
practical threshold.

The original reliable-generation instruction is restored. Its current invariant prompt
hash is `696efa2a9b0e6aa4e51fd7c1c0022cdbd45baea7ae44f0e3a5a1db3454c4e199`.
The optional `RunManifest.prompt_sha256` field, prompt-aware checkpoint key, and report
column remain because they prevent future prompt comparisons from becoming
indistinguishable. Historical manifests continue to validate with `prompt_sha256=None`.

There is no second Phase 19 prompt candidate. The next work is the inherited comparison
and portfolio scope, not another abstention tweak.

## Acceptance-rule accounting

| ADR-0018 condition | Result | Verdict |
|---|---|---|
| Answerable abstentions ≤15 and judge false-abstains ≤11 | 15 and 11 | Pass |
| Paired judge net wins ≥4 | 2 wins, 0 losses, net +2 | **Fail** |
| 10/10 unanswerable; injection safe; Phase 13 green | 10/10; poisoned row correct; all named guards green | Pass |
| Citation ≥57; strict ≥35; 80/80; zero `TOOL_ERR` | 60; 36; 80/80; 0 | Pass |
| Tests, lint, Track-A, CI, corpus | 203 tests; lint clean; Track-A exit 0; CI checked after push; corpus unchanged | Delivery gate |

The candidate is rejected regardless of the delivery gate because adoption required all
five conditions and condition 2 failed.

## Consequences

The experiment is mixed, not a pure null: a seven-line instruction changed 15 answer
rows, reduced model-declared answerable abstentions from 15 to 10, and produced two
paired judge wins without a paired loss. That is useful evidence that answer policy has
leverage. It is not enough evidence to ship this wording under the rule fixed before the
run.

The failure also exposes why `FALSE_ABSTAIN` count alone is not an optimization target.
An assistant can lower it by answering more often while remaining wrong. The paired
judge gate caught exactly that failure mode, though the judge itself remains weak evidence
with only a 20-label validation set.

Because the candidate is not adopted, Phase 18's model and decoding matrices still
describe the shipped prompt. ADR-0016 and ADR-0017 need no historical-only status note or
rerun. The model claim remains “measured against five alternatives; none beat it,” and
the decoding null remains scoped to the retained prompt.

## Evidence

- Baseline manifest:
  `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f`.
- Candidate manifest and answers:
  `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9`.
- Generated candidate artifacts: `reports/phase19_candidate_matrix.md` and
  `reports/phase19_candidate_frontier.svg`.
- Baseline and candidate causal audits:
  `receipts/phase19_abstention_baseline.json` and
  `receipts/phase19_abstention_candidate_d5c5f885d0c9.json`.
- Candidate-side Track-A receipts: safety `phase7_4efa2e4ec293`, guardrails
  `phase13_guardrails_56dd86a4e1e6`, judge validation `phase9_judge_8f5ec119c48e`,
  dense retrieval `phase3_c2a1ee76001e`, hybrid retrieval `phase4_1966922cebd9`, and
  regression passed with zero deltas against distinct baseline `phase4_551b3b20b9f9`.
- Exact McNemar was recomputed from the two manifests' complete `judge_verdicts` arrays:
  2 candidate-only passes, 0 baseline-only passes, 2 discordant rows, two-sided
  exact-binomial `p = 0.500`.
