# ADR-0005: Guardrails custom-first, and the egress guard without a cloud path

2026-08-05 · Status: **accepted**

## Context

Phase 13 formalises the safety behaviour built ad hoc in Phases 5–7 into named,
individually tested guards. SPEC §13 specifies four pipelines — input/ingest,
egress, output — where "each guard is a small pure function returning a
`GuardrailEvent`," and §13.4 requires every guard to be unit-tested, evaluated,
event-logging, and **toggleable in config** so guardrail ablations can be
measured.

The ground is prepared. `GuardrailEvent` already exists in `schemas.py` with
stages `input | ingest | egress | output` and actions
`pass | flag | redact | block | downgrade_to_abstain`. Presidio PII tagging runs
at ingest. `citation_verify` exists from Phase 5 and injection resistance from
Phase 7; both need naming and eventing rather than building. The golden set
carries every category the ACs reference: 6 `guardrail_benign`, 6
`cross_persona`, 8 `adversarial`. `vaultledger/guardrails/{input,egress,output}/`
are empty scaffolding — no legacy to work around. No guardrail toggles exist in
`config.yaml` yet.

Two things force decisions before implementation starts.

**1. SPEC asks for a library choice** — custom guards versus Guardrails-AI or
NeMo Guardrails.

**2. The egress guard has lost its reason to run.** SPEC §13.2 is the
Presidio-redact → placeholder-map-stays-in-process → rehydrate pipeline, and SPEC
says of it: *"This single feature ties the entire product thesis together — build
it well and demo it in the trace viewer."* Its acceptance criterion is **"zero
tagged PII tokens in captured cloud payloads."** ADR-0003 retired the paid tiers,
`cloud.base_url` is gone from config, and the Cloud-Boosted control was removed
in Phase 11. There are no cloud payloads to capture. The AC is unmeasurable as
written, and this is a heavier loss than the Phase 11 tier reduction: that cost a
benchmark row, this touches the feature SPEC calls the thesis-tying one.

A third problem surfaced while checking the ACs — see *Measurement defect* below.

## Options — library choice

**A. Custom-first.** Each guard is a small pure function returning a
`GuardrailEvent`, per §13's own design. No new heavy dependency beyond Presidio,
which is already in use. Every guard is trivially unit-testable, individually
toggleable for ablation, and attributable when something fails. The cost is that
nothing is community-maintained: detector quality is entirely yours, and generic
attack coverage will be narrower than a library's.

**B. Guardrails-AI.** Supplies a validator library, a RAIL spec, and
retry/reask machinery. The retry machinery is the problem: Phase 5 already has a
bounded L1 repair loop with budgets in `config.yaml`, and ADR-0002 rejected
`instructor` for the same reason — a second framework's control flow fighting the
existing one. Its validators are also generic, while the guards that carry the
most weight here are domain-specific: `numeric_verify` recomputes figures against
the SQLite record-of-truth, and `cross_persona_check` compares against tagged PII
spans. Neither can come from a library. Adopting it would add a dependency to
obtain the guards that matter least.

**C. NeMo Guardrails.** Colang dialog rails, strong at conversational flow
control. VaultLedger is single-turn document Q&A with per-answer verification;
dialog management is not the shape of the problem. It is a heavyweight runtime for
a fraction that would actually be used, and it would sit awkwardly over the
existing pipeline.

## Options — the egress guard

**D. Build it; assert on the payload the guard emits.** The valuable mechanism —
redact with stable placeholders, keep the map in-process, rehydrate exactly — is
pure logic and fully testable with no network. The AC becomes "zero tagged PII
tokens in the payload the egress guard emits, and byte-exact rehydration," which
is honestly measurable and exercises the same code. What is lost: nothing
verifies behaviour against a real provider's wire format.

**E. Drop the egress guard as unreachable code.** Honest about there being no
cloud path, and removes code nothing calls. But it discards the feature SPEC
identifies as tying the product thesis together, in exchange for nothing — the
logic costs little and is the strongest privacy story in the project.

**F. Simulate egress against a local second process treated as untrusted.** More
faithful than D in shape. But the extra machinery buys almost no additional
signal over D, since the assertion is about the payload's contents either way,
and it invents infrastructure to test a function.

## Decision

**Choose A + D.** The accepted decision is custom-first guards plus an offline,
captured-payload egress contract.

**Custom-first (A).** Consistent with §13.4's own instruction and with ADR-0002's
precedent of preferring a hand-rolled bounded loop over a framework's control
flow. Presidio remains the only heavy dependency. Every guard: one pure function,
one unit test, one eval, one `GuardrailEvent`, one config toggle. Revisit only if
custom detector coverage proves inadequate against the adversarial set — which is
a measurable trigger, not a matter of taste.

**Build the egress guard, measure what it emits (D).** Restate the AC as: *zero
tagged PII tokens in the payload the egress guard emits, and rehydration restores
the original spans byte-exactly.* Record explicitly that this is not verified
against any real provider, and that the guard has no live caller — it is exercised
by tests and by the trace viewer only. Keep it because the mechanism is the
product thesis in executable form, and because the day a cloud path returns it is
already built and tested.

**Guard inventory and toggles.** Implement §13.1–13.3 as named guards, each with a
`config.yaml` toggle under a new `guardrails:` block, so the ablation chart §13.4
calls for is possible. `citation_verify` (Phase 5) and the injection heuristics
(Phase 7) are wrapped and evented rather than rewritten; wrapping must not change
their measured behaviour, and the Phase 7 injection pass rate is the regression
check on that.

## Measurement defect found while checking the ACs

**"Over-refusal ≤ 5% on `guardrail_benign`" cannot be satisfied as a rate.** The
category has **6 rows** and `thresholds.over_refusal_max` is `0.05`:

| Over-refusals | Rate | Verdict |
|---:|---:|---|
| 0 | 0.000 | pass |
| 1 | **0.167** | fail |
| 2 | 0.333 | fail |

There is no outcome between 0% and 16.7%. The AC is a zero-tolerance bar wearing
a percentage, and at n=6 it has no power to distinguish a well-calibrated guard
from a lucky one. What a clean sweep actually licenses, 95% upper bound on the
true rate given zero observed failures:

| n | 0 failures means the true rate could still be as high as |
|---:|---:|
| 6 | **39.3%** |
| 20 | 13.9% |
| 60 | **4.9%** |

Only at n≈60 does a clean sweep support the sentence "over-refusal ≤ 5%." At
n=6, a guard that wrongly refuses one benign query in three would frequently
still show 0/6.

**Rejected: expanding `guardrail_benign` in place.** The golden set is 80 rows,
10 of them `unanswerable`, so retrieval is scored over the 70 answerable items —
**and all 6 `guardrail_benign` rows sit inside that 70**. Adding 14 rows makes it
84 and shifts `retrieval_recall@20`, `precision@20`, `MRR`, and `hit_rate`
because the *population* changed, not because retrieval did. That breaks the
re-pin procedure used in Phase 12, which was safe only because the metrics came
back bit-identical: here they would genuinely move, with no way to separate "the
population changed" from "retrieval regressed." It would also invalidate the
Phase 3 → Phase 4 comparison (recall `0.9587 → 0.9786`, MRR `0.4974 → 0.7856`),
one of the project's headline measured results. And at n=20 the claim would still
only be "≤ 13.9%" — full cost, claim not bought.

**Decision, two parts:**

1. **Now — report the count, not a rate.** State "0 of 6 benign queries were
   over-refused" and note the sample is underpowered. SPEC's literal "≤ 5%" AC is
   recorded as **not meaningfully tested**, in the same register as Phase 12's
   routing accuracy. It must never be reported as "≤5% over-refusal achieved";
   that reads as a measured rate and is not one.

2. **Later — a separate over-refusal probe set, outside `golden_set.yaml`.**
   Roughly 60 benign queries that plausibly *look* like they should trip the
   advice-steer, PII, or cross-persona guards but must not, scored only by the
   guardrail eval and never entering the retrieval population. The golden-set
   hash never moves, the Phase 3→4 comparison stays intact, and the denominator
   is finally large enough to state a rate honestly. Authoring quality is the
   whole game: rows that are obviously benign inflate the denominator and measure
   nothing.

   Scheduling is the owner's call — Phase 13 if the number is wanted now, or
   deferred alongside Phase 17. Until that set exists, part 1 stands.

## Consequences

**Easier.** No new framework, no control-flow conflict with the Phase 5 repair
loop, every guard attributable when it fires. Ablations are a config toggle rather
than a fork. The egress guard's tests need no network, so they stay deterministic
and run in CI.

**Harder.** All detector quality is yours; generic attack coverage will be
narrower than a maintained library's, and the adversarial set is the only thing
that will tell you. The egress guard is tested but never exercised in production,
which is a class of code that rots quietly — the test is the only thing keeping it
honest.

**Given up explicitly.** No verification against a real provider's wire format.
If a cloud path ever returns, the egress guard needs a live integration test
before it may be described as proven.

**Revisit when** the adversarial pass rate degrades under custom guards, or a
cloud path returns.

## Evidence

- `vaultledger/guardrails/{input,egress,output}/` contain only `__init__.py`,
  inspected 2026-08-05.
- `GuardrailEvent` in `schemas.py` already carries the stages and actions §13
  requires.
- Golden-set category counts, measured: `single_doc` 18, `aggregation` 14,
  `multi_hop` 12, `unanswerable` 10, `adversarial` 8, `cross_persona` 6,
  `global_summary` 6, `guardrail_benign` 6.
- `thresholds.over_refusal_max: 0.05` in `config.yaml`; no `guardrails:` block
  exists yet.
- Over-refusal arithmetic at n=6 computed above: 1/6 = 0.1667 > 0.05. The 95%
  upper bounds are the exact binomial `1 - 0.05^(1/n)`: 39.3% at n=6, 13.9% at
  n=20, 4.9% at n=60. The smallest n at which a single failure still clears a 5%
  bar is n=20.
- Golden set is 80 rows with 10 `unanswerable`; retrieval is scored over the 70
  answerable items, which include all 6 `guardrail_benign` rows. This is why
  expanding that category in place would move retrieval baselines.
- **Not measured:** no guard has been implemented or evaluated. Every claim about
  custom detector quality versus a library's is a reasoned estimate, not a
  measured result.
