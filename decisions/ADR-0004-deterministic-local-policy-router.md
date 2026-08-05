# ADR-0004: Deterministic local-size policy router before a learned router

2026-08-05 · Status: **accepted**

## Context

Phase 12 originally routed across T0–T3 using privacy, category, retrieval
confidence, and remaining API budget. ADR-0003 retired paid hosted T2/T3 and
replaced the cost axis with local latency. That leaves two runnable generation
tiers: T0 (`qwen3:4b`) and T1 (`qwen3:8b`). The golden set still carries the old
labels: 45 T1 and 35 now-invalid T2 labels.

Phase 11 supplied the first evidence about the local tradeoff. On 12
single-document rows, 4B was faster but strict-matched only 16.7%; 8B matched
58.3%. A router that sends every easy lookup to 4B may save latency but is likely
to over-abstain. An escalation can recover quality, but it pays both model
latencies and may be dominated by always using 8B. That null result must remain
possible.

## Options

**A. Learned router now.** Train an embedding or small classifier on the golden
labels. This can fit the 80 examples closely, but the labels themselves are
being changed by this phase. Training and evaluating on one small authored set
would mostly measure memorisation, and there is no held-out routing corpus.

**B. Always use T1.** This is the evidence-backed product default and probably
the strongest latency–quality point. It makes routing accuracy trivial and
builds no escalation mechanism, so it cannot answer Phase 12's actual question.

**C. Deterministic category policy plus bounded escalation.** Start simple
lookups on T0, send complex and safety-sensitive categories to T1, then escalate
T0 once when the observable answer is weak. Compare it with fixed policies. The
rules are inspectable, labels can be derived and reviewed directly, and a poor
frontier result is informative.

## Decision

Choose **C**. Build the deterministic router first; document a learned router as
a later option only after there is more than one labelled evaluation set.

**Initial tier.** `single_doc` and `guardrail_benign` start on T0. Aggregation,
multi-hop, global-summary, adversarial, cross-persona, and unanswerable queries
start on T1. Unknown categories fail closed to T1. A low retrieval confidence
known before generation also promotes the initial choice to T1.

**Labels.** Migrate `expected_tier` to this *initial-routing* policy: 24 T0 rows
(18 `single_doc`, 6 `guardrail_benign`) and 56 T1 rows. The label scores the
router's initial decision, not the tier that ultimately answers after a measured
escalation. This distinction prevents successful recovery from being counted as
a routing error.

**Escalation.** T0 escalates once to T1 on any of: answerable-query abstention,
structured-output exhaustion, an output guard downgrade, or confidence below
`rerank_tau`. Unanswerable queries start on T1, avoiding a pointless second
attempt after a correct abstention. The configured two-escalation ceiling
remains, but a two-tier lineup exposes only one higher tier. Exhaustion returns
the safest viable answer and records the attempted escalation.

**Budget.** The guard remains real even though configured local projected costs
are zero. It filters unaffordable tiers before selection and before escalation;
tests use non-zero projected costs to prove the branch. Production local runs
record `$0.0` as unpriced, not free.

**Policies for the frontier.** Compare four policies over the same cached model
answers: `all_t0`, `all_t1`, `category_static` (initial decision only), and
`policy_router` (category decision plus bounded escalation). Quality uses the
Phase-11 strict lower-bound scorer until Phase 17 supplies validated judge
reasons. The x-axis is gateway latency, and repeated-run spread is required
before interpreting close points because Phase 11 measured roughly 10% p95
movement between identical runs.

## Consequences

**Good.** The router is deterministic, explainable in one sentence, cheap to
evaluate, and independently testable. Privacy is structurally local-only.
Every final answer contains a `RoutingDecision`, and every escalation has a hard
exit.

**Bad.** The 90% routing target is not evidence of learned generalisation: the
same explicit policy defines the labels and the decisions. The useful evidence
is whether the dynamic policy reaches a better latency–quality point than the
fixed baselines. With only two models, it may not.

**Given up.** This phase cannot evaluate routing across hosting/privacy tiers,
dollar budgets, or provider failure. Phase-6 tests preserve the historical
cloud seam, but the Phase-12 product policy never selects it.

**Revisit when** the full Phase-17 model lineup exists, a second independently
labelled routing set exists, or a hosted budget returns. At that point compare a
held-out learned router (RouteLLM-style or embedding similarity) against this
deterministic baseline.
