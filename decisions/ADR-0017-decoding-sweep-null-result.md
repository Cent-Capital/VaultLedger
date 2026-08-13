# ADR-0017: The decoding sweep is null; retain `temperature=0.0 / top_p=0.95`

2026-08-13 · Status: **accepted** · Applies the ADR-0014 preregistered decision rule

## Context

ADR-0014 preregistered a `qwen3:8b` decoding comparison before any cell ran: six
experimental profiles — temperature {0.3, 0.7} × top_p {1.0, 0.9, 0.8} — against the
canonical six-model matrix's `qwen3:8b` cell at `0.0 / 0.95` as the seventh, baseline
profile. Fixed controls: `top_k=20`, `seed=42`, `num_ctx=8192`, `num_predict=768`,
`think=false`, guardrails on, all 80 golden rows, fixed local `qwen3:8b` judge.

All six cells ran to completion: 480 rows, 100% generation coverage on every cell, zero
`TOOL_ERR`, 8,320 s wall, `$0.00` unpriced. Every cell finalised with complete judge
coverage; no checkpoint was retained.

| profile | judge | strict | numeric | citation | abstention | identical | W/L |
|---|---|---|---|---|---|---|---|
| **0.0 / 0.95 (baseline)** | **70.0%** | 43.8% | 35.7% | 71.2% | 76.2% | — | — |
| 0.3 / 1.0 | 68.8% | 43.8% | 35.7% | 71.2% | 77.5% | 95% | 0/1 |
| 0.3 / 0.9 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 98% | 0/2 |
| 0.3 / 0.8 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 96% | 0/2 |
| 0.7 / 1.0 | 68.8% | 43.8% | 35.7% | 71.2% | 76.2% | 90% | 0/1 |
| 0.7 / 0.9 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 89% | 0/2 |
| 0.7 / 0.8 | 67.5% | 43.8% | 35.7% | 72.5% | 77.5% | 88% | 0/2 |

"identical" is the share of the 80 answers byte-identical to the baseline's;
W/L is wins/losses on paired judge verdicts against the baseline.

## Options

**Retain `0.0 / 0.95`.** AC1 of the preregistered rule requires a cell to gain at least
four rows on **both** the strict scorer and the judge. No cell gained a single row on
either. Strict match is 35/80 in all seven profiles and numeric exact-match is 15/42 in
all seven. The rule's own fallback applies: retain the current defaults and report the
sweep as null.

**Adopt the best-scoring cell.** There is no best-scoring cell. The two profiles that
tie the baseline on strict, numeric and citation sit one judge row *below* it. Adopting
any of them would mean changing a shipped default on a metric that moved in the wrong
direction.

**Declare decoding irrelevant and remove the knobs.** Rejected. The knobs are now typed,
recorded in every manifest, and cost nothing to keep. The null is specific to this task,
this corpus and this model; removing the controls would discard the ability to detect
that changing later, and would undo the ADR-0015 parity work that put the same profile
on the product and eval paths.

## Decision

**Retain `temperature=0.0`, `top_p=0.95`, `top_k=20` as the product decoding profile,
and report the sweep as a null result.** No preregistered cell met the rule; the rule was
committed before the data existed and is applied as written.

## Consequences

**The null has a mechanism, and that is the reportable finding.** Sampling was
demonstrably active: the byte-identical share falls cleanly with temperature, 98% → 88%,
so at temperature 0.7 roughly one answer in ten is worded differently from greedy. Yet
**all seven profiles pass exactly the same 35 rows** on strict matching — the same row
identities, symmetric difference zero — and numeric exact-match never moves. Decoding
changes how an answer is phrased; it does not change whether it is correct. On this task
correctness is settled upstream, by what retrieval places in the context and what the
JSON schema permits, before sampling gets a vote. Short factual answers (mean 47
characters) under constrained JSON decoding leave very little sampling entropy to
exploit.

**Every cell drifted slightly worse, and that direction should not be hidden.** Across
the six cells there are 10 discordant judge rows and all 10 favour the baseline; zero
favour any sweep cell. The cells are not independent — they share a baseline and the
same rows — so a pooled p-value would overstate this, and no per-cell comparison is
individually significant (`p` = 0.500 or 1.000 throughout). Treat it as weak evidence in
the direction theory predicts: greedy decoding takes the argmax, so on an extraction task
any deviation is more likely to hurt than help.

**What this does not establish.** One model, one corpus, one seed, 80 synthetic rows,
and a judge whose 20-label validation supports only an at-least-83%-accurate claim. The
result does not generalise to the other five models, to user documents, to OCR-derived
chunks, or to tasks with longer free-text answers where sampling has more room to matter.
It is a null on this configuration, not a general claim that decoding parameters are
inert.

**The knobs stay earning their keep.** `temperature`, `top_p` and `top_k` remain typed
config recorded in every `DecodingProfile`, so any future manifest is self-describing and
this comparison is repeatable at a different model or corpus.

**To revisit:** if the abstention policy changes (see below), re-run this sweep. A system
that abstains less produces more free text, which is exactly the regime where sampling
could begin to matter.

**The larger lever is elsewhere.** The `FALSE_ABSTAIN` pattern that dominated the model
comparison surfaced again here: at `gs_005` the baseline abstained and temperature 0.3
answered. Decoding moved zero rows; abstention keeps moving rows in both experiments. It
remains the strongest open lead and needs its own pass.

## Evidence

All at git `a38d129`, config hash `f8f9b3e473cf`, golden set hash `b59ee2659a17…`, seed
42, guardrails on, judge `ollama/qwen3:8b`, `top_k=20`, cost `$0.00` (unpriced, not
free):

- baseline `0.0/0.95` — `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f`
  (the ADR-0016 matrix cell, not re-run)
- `0.3/1.0` — `phase18_ollama_qwen3_8b_b_hybrid_t0p3_p1_85c45c9d353a`
- `0.3/0.9` — `phase18_ollama_qwen3_8b_b_hybrid_t0p3_p0p9_56aad3c596df`
- `0.3/0.8` — `phase18_ollama_qwen3_8b_b_hybrid_t0p3_p0p8_24454b463767`
- `0.7/1.0` — `phase18_ollama_qwen3_8b_b_hybrid_t0p7_p1_b4d8ec65454b`
- `0.7/0.9` — `phase18_ollama_qwen3_8b_b_hybrid_t0p7_p0p9_d0a54bb65ed1`
- `0.7/0.8` — `phase18_ollama_qwen3_8b_b_hybrid_t0p7_p0p8_797abc772f32`

Generated artifacts: `reports/phase18_decoding_matrix.md`,
`reports/phase18_decoding_frontier.svg`.

The paired McNemar tests, the byte-identical shares and the strict-passing row-set
comparison were computed in review from the committed manifests and answer files; they
are not harness output and are reproducible from those artifacts.
