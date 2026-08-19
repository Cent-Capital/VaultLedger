# Evaluation

The harness is the deliverable. This page defines every metric the project computes, the
population it divides by, and the direction it is biased in.

**Read the bias column before the value column.**

## The golden set

80 hand-authored questions in `vaultledger/evals/golden_set.yaml`, versioned and **SHA-256
hashed** — the hash is recorded in every `RunManifest`, so any edit is detectable.

Each row carries the question, the expected answer, expected document ids, expected verbatim
snippets, a category, a difficulty, and a router tier label.

| Category | Count | What it tests |
|---|---:|---|
| `single_doc` | 18 | One fact from one document |
| `aggregation` | 14 | Sums and totals across documents |
| `multi_hop` | 12 | Comparisons requiring two or more lookups |
| `unanswerable` | 10 | Facts genuinely absent — must abstain |
| `adversarial` | 8 | Prompt injection and hostile content |
| `global_summary` | 6 | Corpus-wide relationship questions |
| `guardrail_benign` | 6 | Legitimate questions a guard might wrongly block |
| `cross_persona` | 6 | Must not leak another person's data |
| **Total** | **80** | 20 easy · 39 medium · 21 hard |

**Only 70 of the 80 rows carry expected documents** — the 10 `unanswerable` rows have none
by construction — so **every retrieval metric divides by 70, not 80.** The manifests record
this as `retrieval_eval_coverage: 0.875`.

`python -m vaultledger.evals validate` checks the hash and confirms every expected snippet
genuinely appears in the corpus.

## Retrieval metrics — computed over the retriever alone, before generation

All at **k = 20**, over the 70 answerable rows. Deterministic; no model judgment involved.

| Metric | Definition | Rewards | Blind to |
|---|---|---|---|
| **recall@20** | expected docs found in top 20 ÷ expected docs, averaged | Finding *all* required evidence | Where in the list it landed |
| **precision@20** | relevant in top 20 ÷ results returned, averaged | Not returning junk | Whether you missed anything |
| **MRR** | mean of 1 ÷ (rank of first relevant result) | Getting the answer to the **top** | Everything after the first hit |
| **hit rate@20** | fraction of questions with ≥1 relevant result | Finding *anything* | How much, and where |

### Reading the numbers honestly

- **precision@20 is ≈0.10 and that is not a failure.** Most questions expect **one**
  document. Return 20 results with exactly one correct and precision is capped at 0.05 *even
  for a perfect retriever*. The ceiling is set by the ratio of expected documents to k. It
  is reported anyway and no decision is made on it.
- **recall@20 of 0.9786 is inflated by the setting.** Retrieving 20 of 60 documents means a
  third of the corpus is already in hand. This number would look entirely different against
  60,000 documents.
- **MRR is where the Phase 4 result actually lives.** `0.4974 → 0.7856` means the first
  relevant result moved from roughly rank 2 to usually rank 1. Hit rate was **identical**
  across the dense, fusion-only, and reranked arms — fusion and reranking mostly **reorder**
  evidence rather than find more of it.

### k=20 for evaluation, top-6 for answering

These are different knobs and conflating them tanks citation precision. Phase 5's first live
probes abstained on trivially answerable questions because the harness fed the generator
twenty near-identical statements; at `answer_top_n=6` the same model emitted a perfect
citation. **More context is not automatically better.**

### The failure record

A shortfall emits a `RANK_MISS` failure **naming the exact missing document**, so the count
is an investigable backlog rather than a number.

## Generation metrics — one scorer, called from every path

All four live in `score_answer()` in `vaultledger/evals/matrix.py`. The live matrix and the
offline `rescore` path both call it, so a baseline recomputed from a committed receipt and a
fresh cell are comparable **by construction** rather than by a number someone pasted between
them.

| Metric | Rule | Population | **Bias** |
|---|---|---|---|
| `strict_answer_match` | every literal anchor (amount/date/identifier) from the reference present after normalisation | 80 rows | **Under-credits** paraphrase — *and is confounded with verbosity* |
| `numeric_exact_match` | every reference quantity present within `ε = 0.01` | rows whose reference carries a quantity | **Over-credits** — a presence test, not a usage test |
| `citation_doc_hit` | ≥1 cited document in the expected set | 80 rows | Document-level only; says nothing about support |
| `abstention_accuracy` | `abstained == (category == "unanswerable")` | 80 rows | `unanswerable` is a free 100% |

**The pairing is the point.** Strict match under-credits; numeric exact match over-credits.
Read together they bracket the truth. Read alone, you can pick the flattering one.

### Two confounds, recorded rather than hidden

**Verbosity.** Across the six bake-off models, mean answer length and strict rate rise
together — 37 characters / 8% up to 72 characters / 54%. A longer answer has more
opportunity to contain the literal anchor, including among wrong candidates. So
`gemma3:12b`'s 10-point strict lead over `qwen3:8b` is **not** a 10-point correctness lead.

**Recited citations.** A model appending a `Citations:` block to `answer_text` can satisfy
the numeric scorer with figures its prose never stated. Variant B does this on 0 of 160
committed rows, so the help is one-sided. Phase 14 therefore reports its margins **twice** —
as scored, and with the block stripped — and says the stripped column is the one to quote.

### `unanswerable` is a floor, not a strength

Five of six bake-off models score 100% there. Abstaining wins that category for free.
`gemma3:1b` scores 80% on `unanswerable` while scoring 26% overall.

## The abstention confusion matrix

|  | Question answerable | Question unanswerable |
|---|---|---|
| **Answered** | `answered_right` / `answered_wrong` | `answered_wrong` → **`ABSTAIN_FN`** |
| **Abstained** | `wrongly_abstained` → **`ABSTAIN_FP`** | `rightly_abstained` |

Derived: `abstention_unanswerable_recall`, `abstention_answerable_specificity`,
`abstention_eval_coverage`.

**Rows with no recorded outcome become explicit `TOOL_ERR` failures — never silently dropped
from the denominator.** Shrinking a denominator to hide a failure is the easiest way to lie
with a metric, and the code refuses to do it.

`ABSTAIN_FP` — abstaining on an answerable question — is the **dominant failure category**
in this project and its largest known open lever.

## LLM-as-judge

A judge is a classifier, and an unvalidated classifier is not evidence. An always-PASS judge
looks perfect on correct answers; an always-FAIL judge looks perfect on wrong ones. So both
error directions are measured separately.

- `judge/human_labels.yaml` — exactly 20 manually classified answers, balanced 10 acceptable
  / 10 unacceptable.
- `rubric_v1.md` — versioned and hashed. PASS requires **both** semantic correctness **and**
  complete evidence support.
- **TPR** = TP ÷ (TP + FN) — of genuinely good answers, how many passed?
- **TNR** = TN ÷ (TN + FP) — of genuinely bad answers, how many were caught?
- `make judge-validate` **exits non-zero unless both exceed 0.80.**

**Measured: TPR 1.00, TNR 1.00.** And four caveats travel with it everywhere:

1. The labels are clear boundary cases, not a sampled production distribution.
2. SPEC's own rule applies — *100% pass means the suite is too easy.*
3. There is **no headroom to detect a judge getting worse**. A gate at a ceiling cannot ring.
4. **20 labels support only an "at least 83% accurate" claim, and a null classifier scores
   19/20 on that same set.**

Every downstream use therefore carries the phrase **"the judge remains weak evidence."**

Verdicts are stored with a required `reason` and a failure code from a fixed set
(`NONE`, `INCORRECT`, `UNSUPPORTED`, `FALSE_ABSTAIN`, `INJECTION`, `OTHER`). That reason
field is what surfaced `FALSE_ABSTAIN` as the dominant lever — an aggregate pass rate never
could have.

## Latency

Two flavours, not interchangeable: **gateway latency** (inside the model call) and **wall
latency** (end to end). Manifests record both.

**p50 means median** — the value half the requests beat. **p95** is the 95th percentile.
The reports always print p95 beside the median, because medians hide the tail.

### Three caveats that must travel with any latency figure

1. **This harness cannot rank models by latency.** Phase 13 measured ~50% p50 movement
   between two arms that produced *byte-identical answers*. Guards add work; they cannot make
   a model 57% faster. Two earlier rankings were formally **withdrawn** (ADR-0003 amendment 2).
2. **At small n, p95 is just the slowest row.** At n≈6 the 95th percentile is the maximum.
   Phase 15's report names which single row produced each figure.
3. **Latency is computed over completed rows only.** A timed-out row is excluded entirely,
   so a slow arm's reported tail can *understate* its real behaviour, and two arms with
   different completion rates have unequal denominators. The generated report discloses this.

## Cost

`total_cost_usd: 0.00` on every run, because every model is local.

The phrasing rule everywhere: **"unpriced, not free."** Electricity, hardware, and — for
example — the 45.8 minutes of local inference behind one LightRAG index build are real costs
that produce no invoice. Configured provider rates default to zero meaning *not priced*,
never *the provider is free*.

## Statistics

**Paired comparisons.** When two systems answered the same rows, compare row by row, not
total to total. In the six-model bake-off the top two agreed on 70 of 80 rows; the entire
comparison lived in the 10 they disagreed on, which split 6–4. *"The two-point gap in the
totals was never two points of quality; it was one and a half rows of noise."*

**McNemar's test** looks only at discordant pairs. Measured against `qwen3:8b`:
`gemma3:12b` 6/4 (p=0.754), `qwen3:14b` 3/8 (p=0.227), `gemma3:4b` 2/13 (p=0.007),
`qwen3:4b` 5/19 (p=0.007), `gemma3:1b` 1/36 (p<0.001).

**Bonferroni.** Five comparisons at α=0.05 gives ~23% chance of a false alarm, so the
threshold becomes 0.01. The three significant losses survive; the two nulls are unaffected.

**A large p-value is not equivalence.** `p=0.754` is absence of evidence. Ten discordant
pairs give low power — only a large effect would have surfaced.

**The rule of three.** With **zero** failures in *n* trials, the exact 95% upper bound on the
true rate is `1 − 0.05^(1/n)`:

| n | 0 failures bounds the true rate at |
|---:|---:|
| 6 | **39.3%** |
| 20 | 13.9% |
| 60 | **4.9%** |

This is why over-refusal is reported as **"0 of 6, not meaningfully tested"** and never as
"≤5% achieved." And why expanding `guardrail_benign` in place was **rejected**: all six of
those rows sit inside the 70 answerable rows, so adding rows would move every retrieval
metric because the *population* changed. **Never change a benchmark's population to fix a
different metric's power problem.**

## Run manifests

Every run writes a `RunManifest`: `run_id`, timestamp, `git_sha`, `config_hash`,
`golden_set_hash`, `seed`, variant, model, metrics, `total_cost_usd`, taxonomy-coded
failures, plus optional `DecodingProfile`, `prompt_sha256`, `ModelMetadata`, judge model and
judge verdicts with reasons.

**If a chart cannot cite its run id, it does not ship.**

## The regression runner

`regression_baseline.json` pins metric policies to a measured manifest and a frozen golden
hash. `make regression` writes a delta report and exits non-zero on any drop beyond its
metric-specific threshold.

- **Missing metrics fail closed.** A metric that vanishes is a failure, not a pass.
- **Incompatible golden hashes raise** rather than being silently compared.
- **A manifest whose run id equals the baseline's raises**, because comparing a run against
  itself produces perfect zeros and proves only that the file parsed.
- The negative control is a **genuine measured degradation** (the Phase-3 dense manifest),
  not just an edited number — it flags recall@20 and MRR, leaves precision and hit rate
  green, and exits 1.

**A green report with all-zero deltas is meaningful only because the run ids differ.**

## The failure taxonomy

Every failure carries exactly one primary code: `RETR_MISS`, `RANK_MISS`, `CTX_OVERFLOW`,
`GEN_HALLUC`, `GEN_FORMAT`, `CITE_FAIL`, `NUM_MISMATCH`, `ABSTAIN_FP`, `ABSTAIN_FN`,
`GUARD_FP`, `GUARD_FN`, `ROUTE_ERR`, `TOOL_ERR`, `GRAPH_MISS`.

`make failure-pareto` builds the sequence, with snapshots **discovered by rule** — matching
variant, model, golden hash, and row population, on the shipped prompt and decoding profile,
one snapshot per config hash — so re-runs at one configuration cannot pad a flat sequence.

**The requested shrinking-bars picture is not supported and the artifact says so.** The
shipped arm runs 48 → 48 → 47; `qwen3:4b` runs 49 → 49 → 55. The informative part is the
*composition*: `NUM_MISMATCH` fell 17 → 14 while `ABSTAIN_FP` rose 16 → 19. The system got
better at arithmetic and more reluctant to answer — invisible in the total, obvious in the
breakdown.

## Preregistration

Six ADRs fix the population, the metric, and the decision rule **before** the data exists.
This is what makes the null and rejected results trustworthy.

Four improvement candidates were built, measured, and **rejected** by rules fixed in
advance — and every one of them would have shipped without those rules:

| Candidate | What it achieved | Why it was rejected |
|---|---|---|
| Evidence-first prompt (ADR-0019) | Abstentions 19→15, judge false-abstains 15→11, five metrics up, none down | Paired judge net **+2** against a required **+4**. Three of four newly answered rows merely turned `FALSE_ABSTAIN` → `INCORRECT` |
| Entity-coverage verifier (ADR-0021) | Caught the exact fabrication it targeted | Replay over **1,040 committed rows** showed it would retract **28** rows that already passed both judge and strict scorer |
| Empty-SQL contract (ADR-0022) | Fixed the target row `mh_009` | Five committed strict passes stopped passing; one budget-exhaustion `TOOL_ERR` |
| Payload-only retest (ADR-0024) | Target row handled honestly | One paired strict loss inside the intervention scope; four `TOOL_ERR`s |

**The rule is conjunctive and gains may not be netted against losses.** No second candidate
is tuned on the same rows — that would be golden-set fitting, not a test.

## What a null result has to show

From ADR-0017, the template worth reusing:

> A null is only worth reporting if you can show the thing you varied actually did
> something. Here it did — the share of answers byte-identical to greedy falls cleanly from
> 98% to 88% as temperature rises, so roughly one answer in ten is worded differently. And
> yet **all seven profiles pass exactly the same 35 rows** — the same row identities,
> symmetric difference zero. Visible change in the input, zero change in the outcome. That
> combination is what separates *"decoding does not matter for this task"* from *"the sweep
> was misconfigured."*
