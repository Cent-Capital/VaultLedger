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

## Amendment — 2026-08-05: the category→tier map is contradicted by its own source data

Found during the pre-Phase-14 review. This ADR set the initial-routing policy on
intuition — "simple lookups on T0, complex and safety-sensitive on T1" — and no
per-category measurement existed to check it against, because the matrix only
emitted aggregate metrics. Computing per-category strict match offline from the
committed answer receipts (`61802221d874`, `33c0a0d50c76` — the exact guards-off
cells the router eval consumed) shows the mapping is backwards on the majority of
the golden set:

| category | n | T0 `qwen3:4b` | T1 `qwen3:8b` | this ADR routes to | better model |
|---|---:|---:|---:|---|---|
| `single_doc` | 18 | 33.3% | **66.7%** | T0 (4B) | 8B — **mismatch** |
| `aggregation` | 14 | **28.6%** | 14.3% | T1 (8B) | 4B — **mismatch** |
| `multi_hop` | 12 | **16.7%** | 0.0% | T1 (8B) | 4B — **mismatch** |
| `guardrail_benign` | 6 | **100.0%** | 50.0% | T0 (4B) | 4B — correct |
| `adversarial` | 8 | 12.5% | **25.0%** | T1 (8B) | 8B — correct |
| `cross_persona` | 6 | 50.0% | **83.3%** | T1 (8B) | 8B — correct |
| `global_summary` | 6 | 0.0% | 0.0% | T1 (8B) | tie |
| `unanswerable` | 10 | 100.0% | 100.0% | T1 (8B) | tie |

**44 of 80 rows are routed to the weaker model for their category.** The premise —
that a bigger model is better on harder categories — does not hold here: 8B is
markedly better at single-document lookup, while 4B is better at aggregation and
multi-hop. The aggregate scores (4B 40.0%, 8B 42.5%) hide this completely, which
is exactly why aggregate-only metrics were the enabling condition for the error.

This also explains the router's modest headline: `policy_router` reached 47.5%
strict match against `all_t1`'s 42.5%. Some of that five-point gain is escalation
recovering from initial choices this table says were wrong to begin with.

**Not corrected here, deliberately.** Flipping the map would be fitting the policy
to the same 80 rows that scored it, which is the circularity this ADR already
carries on the labels. A corrected map has to be justified on a held-out set, or
stated openly as fitted and its accuracy claim withdrawn.

**Consequences recorded now:**
- Phase 12's `routing_accuracy` remains **met in form only**, and this amendment
  adds a second reason: the labels encode a mapping the data contradicts, so 100%
  agreement measures conformance to a policy that is likely wrong, not routing
  quality.
- The `category_static` and `policy_router` numbers stand as measured; their
  *interpretation* changes. The router is not near a ceiling — it is leaving
  points on the table.
- **Phase 17 owes a per-category re-derivation of the map** across the full local
  lineup, with the fitted-versus-held-out distinction made explicit.
- The matrix must emit per-category metrics so this class of error is visible
  without an offline script. Tracked as pre-Phase-14 work.
