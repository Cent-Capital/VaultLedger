# ADR-0016: Retain `qwen3:8b` after the six-model local bake-off

2026-08-13 · Status: **accepted** · Implements the ADR-0014 preregistration; discharges
the ADR-0011 prohibition

## Context

ADR-0011 recorded that only one model family had ever been evaluated — 32 committed
runs on `qwen3:8b`, 5 on `qwen3:4b`, zero Gemma — and forbade any claim that
`qwen3:8b` is the best available local model. It was only the model the system was
built and measured on.

Phase 18 ran the preregistered comparison: six models, two families × three sizes, all
80 synthetic golden rows, `B_hybrid`, guardrails on, seed 42, a fixed local
`qwen3:8b` judge, and one identical decoding profile for every candidate
(`temperature=0.0`, `top_p=0.95`, `top_k=20`, `num_ctx=8192`, `num_predict=768`,
`think=false`). Every cell completed all 80 rows at 100% generation coverage with zero
`TOOL_ERR`. Total wall time 8,957 s.

Because every candidate answered the same 80 rows, the comparisons are **paired**, and
the aggregate rates below are not the right test.

| model | judge | strict | citation | abstention | median | p95 | resident |
|---|---|---|---|---|---|---|---|
| gemma3:12b | 72% | 54% | 68% | 72% | 31.9 s | 57.3 s | 8.0 GB |
| **qwen3:8b** | **70%** | 44% | **71%** | **76%** | **7.2 s** | **13.3 s** | 6.6 GB |
| qwen3:14b | 64% | 46% | 62% | 66% | 27.0 s | 46.8 s | 10.3 GB |
| gemma3:4b | 56% | 41% | 56% | 61% | 4.6 s | 9.0 s | 3.9 GB |
| qwen3:4b | 52% | 34% | 48% | 50% | 4.0 s | 9.9 s | 3.8 GB |
| gemma3:1b | 26% | 8% | 20% | 24% | 1.9 s | 4.0 s | 0.9 GB |

Exact McNemar on the paired judge verdicts, two-sided, each against `qwen3:8b`:

| vs `qwen3:8b` | wins | losses | discordant | p |
|---|---|---|---|---|
| gemma3:12b | 6 | 4 | 10 | 0.754 |
| qwen3:14b | 3 | 8 | 11 | 0.227 |
| gemma3:4b | 2 | 13 | 15 | 0.007 |
| qwen3:4b | 5 | 19 | 24 | 0.007 |
| gemma3:1b | 1 | 36 | 37 | <0.001 |

Five comparisons; under a Bonferroni threshold of α = 0.01 the three significant
results hold and the two null results are unaffected.

## Options

**Retain `qwen3:8b`.** No candidate beat it. The two that are statistically
indistinguishable from it cost 3.7–4.4× the median latency and more resident memory,
and `qwen3:8b` leads outright on the two grounding metrics — citation-document hit and
abstention accuracy — that matter most for a document-QA product.

**Switch to `gemma3:12b`.** It tops the aggregate judge rate by two points. That is 10
disagreeing rows split 6–4, `p = 0.754` — a coin flip. Buying a null result for 4.4×
the latency and 1.4 GB more resident memory is a cost with no measured benefit. Its
10-point lead on strict matching is confounded (see Consequences).

**Switch to `qwen3:14b`.** The same-family scale-up lost 8 rows and won 3. It is
nominally worse on every quality metric while being 3.75× slower and 3.7 GB larger.
Nothing recommends it.

**Route per category.** Per-category winners do differ — `gemma3:12b` leads
`multi_hop` (50% vs 42%) and `adversarial` (50% vs 38%); `qwen3:8b` leads `single_doc`
(89% vs 83%) and ties `cross_persona` at 100%. Category cells hold 6–18 rows, so these
are single-digit differences on tiny samples. Fitting a routing map to them would be
fitting noise on the same rows used to discover it.

## Decision

**Retain `ollama/qwen3:8b` as the product generation model.** No alternative beat it on
a preregistered, paired, full-population comparison; three were significantly worse; the
two that tied are substantially more expensive and lose on the grounding metrics.

The reader-facing claim changes from *"the model the system was built on"* to
**"measured against five alternatives across two families and three sizes; none beat
it."** It does **not** become "the best available local model" — see below.

`gemma3:1b` is recorded as unusable for this product at 26% judge / 8% strict.

## Consequences

**What this licenses.** ADR-0011's prohibition is discharged to exactly the strength of
the evidence: not-beaten, not best. Six model families/sizes now have committed
manifests, so the model axis is no longer a blind spot.

**What it does not license.** `p = 0.754` is absence of evidence, not evidence of
equivalence. Ten discordant pairs give low power; only a large effect would have been
detectable. This is one run, one seed, 80 synthetic rows, and a judge whose own 20-label
validation supports only an at-least-83%-accurate claim — a null classifier scores 19/20
on that same set. McNemar inherits any systematic bias in that judge.

**The strict-match gap is confounded with verbosity.** Mean answer length and strict
rate rise together across all six models (37 → 72 characters, 8% → 54%). Since
`strict_answer_match` is a literal-anchor scorer, a longer answer has more opportunity to
contain the anchor. The 10-point strict gap between `gemma3:12b` and `qwen3:8b` must not
be read as a 10-point correctness gap.

**No latency ranking is claimed.** Phase 13 measured ~50% p50 movement between runs
producing byte-identical answers. This run does **not** re-measure that: each cell ran
exactly once, so run-to-run variance was not observed here and the Phase 13 caveat
stands on its own prior evidence. What this run does show is large *row-to-row* spread
inside a cell — `qwen3:14b` has a 188 s row against a 27 s median, `gemma3:12b` a 185 s
row against 31.9 s. Comparing the first and last 40 rows of each cell gives ratios of
0.65–1.04, i.e. no systematic drift over the course of a cell. Latency here is
descriptive, and because medians hide that tail, p95 travels beside median in every
artifact.

**The most actionable finding is not about models.** Of the 10 rows separating the top
two candidates, **five are `FALSE_ABSTAIN`** — the system declined to answer when the
reference answer was available. That is consistent with the known-open defect that
abstention fires whenever zero citations survive, and that `verify_citations` only
confirms a snippet *exists* rather than that it *supports* the answer. Model choice moved
2 points; the abstention policy is plausibly worth more. It is the next thing to
investigate, and it needs its own pass.

**`unanswerable` is a ceiling artifact.** Five of six models score 100% there, including
`qwen3:4b` at 100% overall-52%. Abstaining wins that category for free, so aggressive
abstention inflates it while costing everything else — `gemma3:1b` scores 80% on
`unanswerable` and 26% overall. Read that column as a floor, not a strength.

**To revisit:** if the abstention pass lands, re-run the two null cells — a system that
abstains less may separate `gemma3:12b` and `qwen3:8b` differently.

## Evidence

All manifests at git `42b5110`, config hash `f8f9b3e473cf`, golden set hash
`b59ee2659a17…`, seed 42, guardrails on, judge `ollama/qwen3:8b`, cost `$0.00`
(unpriced, not free):

- `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f` — 8.2B, Q4_K_M
- `phase18_ollama_gemma3_12b_b_hybrid_t0_p0p95_e4080a7744a2` — 12.2B, Q4_K_M
- `phase18_ollama_qwen3_14b_b_hybrid_t0_p0p95_86a02e29ddbe` — 14.8B, Q4_K_M
- `phase18_ollama_gemma3_4b_b_hybrid_t0_p0p95_be40611af1d1` — 4.3B, Q4_K_M
- `phase18_ollama_qwen3_4b_b_hybrid_t0_p0p95_cc0a66413693` — 4.0B, Q4_K_M
- `phase18_ollama_gemma3_1b_b_hybrid_t0_p0p95_15e766367545` — 999.89M, Q4_K_M

Generated artifacts: `reports/model_matrix.md`, `reports/model_frontier.svg`.

The McNemar tests were computed in review from the `judge_verdicts` arrays in the six
manifests above; they are not produced by the harness and are reproducible from the
committed manifests.

The preregistered `qwen3:8b` decoding sweep (ADR-0014) has **not** run. This ADR settles
the model axis only.
