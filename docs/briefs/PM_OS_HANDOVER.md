# VaultLedger → PM-OS handover

2026-08-14 · Repo at `fd1aa98`, pushed, CI green (run 31849255563) · Historical handover
for narrative work maintained outside this repository

**The rule this document exists to enforce.** The repo is the single source of truth for
every number. This is a claim register with pointers, not a second copy of the data. When
PM-OS states a figure, it should trace to a manifest id or receipt named here. Do not
restate a number that has drifted from its source, and do not upgrade a boundary because
it reads better on a slide.

---

## 1. Claims you can make, with their exact boundaries

### The model bake-off — a null that vindicates the incumbent

Six local models, two families × three sizes, all 80 golden rows each — **480 rows, 100%
generation coverage, zero tool errors, 2.49 hours, $0.00 (unpriced, not free)**.

**No model beat the shipped `qwen3:8b`.** Exact McNemar on paired judge verdicts over the
identical 80 rows:

| vs qwen3:8b | wins | losses | p |
|---|---|---|---|
| gemma3:12b | 6 | 4 | 0.754 |
| qwen3:14b | 3 | 8 | 0.227 |
| gemma3:4b | 2 | 13 | 0.007 |
| qwen3:4b | 5 | 19 | 0.007 |
| gemma3:1b | 1 | 36 | <0.001 |

Five comparisons, Bonferroni threshold α = 0.01; the three significant losses hold.

Say it as: **"measured against five alternatives across two families and three sizes;
none beat it."** The two that tied cost **3.7–4.4× the median latency**, and `qwen3:8b`
leads outright on citation-document hit (71.2%) and abstention accuracy (76.2%) — the two
grounding metrics. Scaling did not help: `qwen3:14b` lost 8 rows and won 3 against its
smaller sibling.

Source: ADR-0016, six `phase18_*_b_hybrid_t0_p0p95_*` manifests, `reports/model_matrix.md`.

### The decoding sweep — a null with a mechanism

Six preregistered profiles against the retained `0.0 / 0.95` baseline. **No profile won.**
The mechanism is the interesting part: the share of answers byte-identical to greedy falls
cleanly from 98% to 88% as temperature rises, so sampling was demonstrably active — and
**all seven profiles pass exactly the same 35 strict rows**, symmetric difference zero,
with numeric exact-match frozen at 15/42 throughout.

The line worth using: *the experiment reworded a tenth of the answers and changed the
score on none of them.* Correctness is settled upstream by retrieval and the JSON schema
before sampling gets a vote.

Source: ADR-0017, six `phase18_*_t0p*` manifests, `reports/phase18_decoding_matrix.md`.

### The abstention investigation — three experiments, all rejected

A causal audit found **19 answerable abstentions: 15 model-declared, 3 guard downgrades,
1 query block** — correcting the earlier assumption that the citation verifier was the
cause. All 19 retrieval scores were above `rerank_tau`, so SPEC's L2 widen-retry would
have fired on none of them.

Two candidates followed, both rejected against rules fixed before the data existed:

- **Evidence-first prompt (ADR-0019).** Passed five of six gates with zero regressions;
  rejected on paired judge net wins of **+2 against a required +4**. Four rows stopped
  abstaining — one became correct, **three became wrong answers**. The conjunctive rule
  caught a metric improving while behaviour worsened.
- **Entity-coverage verifier (ADR-0021).** Rejected on the binding zero-false-positive
  gate: **28 retractions of rows already passing both judge and strict**, measured by
  deterministic replay over 1,040 stored answers with no generation calls.

Source: ADR-0018/0019/0020/0021, `receipts/phase19_abstention_baseline.json`,
`receipts/support_coverage_replay.json`.

### The failure profile rotated; it did not shrink

Identical 80-row population (golden hash `b59ee265`), `qwen3:8b`, three pipeline
configurations across the Phase 11→18 arc:

| taxonomy | phase11 | phase11 (guard on) | phase18 |
|---|---|---|---|
| ABSTAIN_FP | 16 | 17 | **19** ↑ |
| NUM_MISMATCH | 17 | 16 | **14** ↓ |
| TOOL_ERR | 1 | 1 | **0** ↓ |
| GEN_HALLUC | 12 | 12 | **12** — |
| CITE_FAIL | 2 | 2 | **2** — |
| **total** | **48** | **48** | **47** |

Numeric accuracy improved and tool errors were eliminated; false abstention grew and
overtook numeric mismatch as the top failure mode. **Hallucination never moved** — twelve
rows, three configurations, zero change.

SPEC asked for shrinking Pareto bars. The data does not support that story and the
artifact must say so. What it supports is better: the profile rotated, and the engineering
traded one failure mode for another.

Source: my survey of committed manifests, 2026-08-14. The generator for this artifact is
not yet built.

---

## 2. Claims you must not make

- **Not "the best available local model."** The evidence is not-beaten, not best.
  `p` = 0.754 is **absence of evidence, not equivalence** — ten discordant pairs give low
  power and only a large effect would have shown.
- **Not "decoding doesn't matter."** It is null *on this task, this corpus, one seed, one
  model*, and the mechanism (short factual answers under constrained JSON) is why.
- **No latency ranking.** Phase 13 measured ~50% run-to-run p50 movement between runs
  producing byte-identical answers, and it was not re-measured — each cell ran once. Cite
  latency as descriptive, always with p95 beside median.
- **The judge is weak evidence.** Its 20-label validation supports "≥83% accurate"; a null
  classifier scores 19/20 on the same set. Every judge-derived number inherits that.
- **`strict_answer_match` is a literal-anchor scorer, not a lower bound.** It is confounded
  with verbosity: answer length and strict rate rise together across all six models
  (37 → 72 characters, 8% → 54%).
- **Phase 15 has two scoring schemes; do not mix them.** Strict is **73.3% recall /
  13.6% precision** (11/15 and 11/81). The ADR-0009 alias-aware secondary is **100% recall
  / 18.5% precision** (15/15 and 15/81). Taking the recall from one and the precision from
  the other flatters the result, because it pairs the stricter recall with the looser
  precision. `PROGRESS.md` and `README.md` both handle this correctly;
  `PHASE18_KICKOFF_BRIEF.md` carried the mixed pairing and was corrected on 2026-08-14.
  Source: ADR-0010 §62–63.
- **No OCR accuracy claim.** One cleanly rendered image-only page was exercised.
- **Phase 17 is closed on a waiver (ADR-0013).** "Phases 0–19 closed" overstates it.
- **`$0.00` means unpriced, not free.**

---

## 3. The narrative spine

The honest arc is not "I built a RAG app and made it better." Every improvement attempt
failed. The arc is:

**A system was built, then subjected to four preregistered experiments designed to
displace its own defaults — and it survived all four.** Two models and six decoding
profiles could not beat the incumbent. Two candidate fixes to the dominant failure mode
were rejected by rules written before the data existed, including one that passed five of
six gates and one that caught the exact fabrication it was designed to catch.

That is a stronger claim than a graph going up, and it is much harder to fake. The
supporting detail worth telling:

- **The rules held under pressure.** ADR-0019's candidate improved on everything and
  regressed on nothing. It was rejected because a preregistered threshold said +4 and it
  delivered +2. Adopting it would have shipped three new wrong answers.
- **A metric improved while behaviour worsened.** False abstentions fell by exactly four;
  three of those four rows became incorrect. The conjunctive rule is what caught it.
- **The failed guard taught something the successes didn't.** 27 of its 28 false positives
  were correct answers naming real entities found in *retrieved but uncited* chunks — the
  model's citation selection is narrower than its evidence use. That is a real
  characterisation of the pipeline, obtained from a rejected experiment.
- **The blind spot was measured, not assumed.** Hallucination stayed at exactly 12 rows
  across three configurations while everything else moved.

---

## 4. What is still owed — say it, don't hide it

- **Phase 17's machine half (ADR-0013).** No fresh macOS Administrator-account install has
  been run; `receipts/phase17_machine_half.md` does not exist. Checklist A5–A7 and an
  independent non-technical five-minute cold read remain outstanding. **Never describe the
  development-account or clean-virtualenv receipt as that machine half, and never write
  "installs cleanly on a fresh Mac."**
- **Phase 19 portfolio scope.** Variant matrix, Pareto sequence, ADR index, demo v2, and
  the DoD truth table are unbuilt.
- **Variant coverage is not rectangular.** A_naive has **zero** generation rows — it was
  never measured for generation. B has 80, C has 6, D has 26. C and D predate ADR-0015's
  transport change and carry no decoding block, so they describe the old LiteLLM chat path,
  not the shipped product. Only B describes the current system.
- **The support defect is open.** Verbatim citation existence is not entailment; a valid
  citation can still sit behind an unsupported entity.
- **Known-open, each needing its own pass:** `numeric_verify` and `cross_persona_check`
  pass on empty populations; the agent time budget is polled at loop boundaries rather than
  enforced in flight; `routing_accuracy = 100%` is a tautology.

---

## 5. Source index

| Claim area | Primary sources |
|---|---|
| Model selection | ADR-0016 · `phase18_*_b_hybrid_t0_p0p95_*` · `reports/model_matrix.md` |
| Decoding | ADR-0017 · `phase18_*_t0p*` · `reports/phase18_decoding_matrix.md` |
| Abstention causes | ADR-0018 · `receipts/phase19_abstention_baseline.json` |
| Prompt candidate | ADR-0019 · `phase18_…_d5c5f885d0c9` |
| Verifier candidate | ADR-0020/0021 · `receipts/support_coverage_replay.json` |
| Waivers | ADR-0010 (Phase 15, measured-and-missed) · ADR-0013 (Phase 17, unattempted) |
| Build log | `PROGRESS.md`, appended per phase, never backdated |

Frozen baseline for every Phase 18/19 comparison:
`phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f` — 56 judge passes, 35 strict,
57 citation hits, 61 correct abstention decisions, 80/80 coverage, zero tool errors.

Synthetic corpus hash, unchanged throughout:
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`.
