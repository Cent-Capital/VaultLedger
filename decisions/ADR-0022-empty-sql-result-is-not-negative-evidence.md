# ADR-0022: An empty SQL result is not negative evidence

2026-08-15 · Status: **accepted** · Outcome: contract rejected after measurement

## Context

Variant D exposes read-only SQL results to its bounded planner. An empty result currently
contains columns, an empty `rows` array, provenance, and truncation state, but no semantic
instruction. The planner has treated that silence as evidence that a fact is false or one
amount is smaller than another. In the committed Phase 11 receipt, `mh_009` therefore
asserts a false comparison after an attempted join returns no rows.

The empty set only establishes that the submitted query matched nothing. It does not
distinguish a genuinely absent fact from an invalid join path, an over-constrained query,
or evidence that must be gathered through separate lookups. Empty results remain valid
tool outcomes: some questions, such as duplicate detection, legitimately produce none.

## Decision

When `SqlResult.summary()` serializes zero rows, it will add:

```json
{
  "result": "NO_ROWS_RETURNED",
  "interpretation": "An empty result means this query matched nothing. It is NOT evidence that the fact is false, absent, or smaller. Do not state a negative or comparative conclusion from an empty result. Re-query more simply, split a join into separate lookups, or use retrieve."
}
```

The same instruction will appear in the planner's SQL tool description so it is present
before the first query. Empty results will not raise `AgentToolError`, and non-empty result
summaries will not change. No schema, query-template, retrieval, or guard behavior changes.

## Adoption rule

Adopt the contract only if a paired rerun of the same 26 aggregation and multi-hop rows,
using `ollama/qwen3:8b` and the committed decoding profile, satisfies every condition:

1. `mh_009` no longer draws a negative or comparative conclusion from an empty result; it
   either answers correctly or abstains honestly.
2. No row that passes the committed strict scorer starts failing.
3. Coverage is 26/26 with zero `TOOL_ERR`.
4. `make test` and `make lint` pass, and the synthetic corpus hash is unchanged.

Accuracy is explicitly not an adoption criterion. Turning a false assertion into an honest
abstention may leave aggregate accuracy unchanged. Any strict or judge movement is an
observation only, not the justification for adoption.

## Measurement

The result record will quote `mh_009` before and after verbatim, count rows with an empty SQL
result in each arm, and report the planner's next action after every such result. If `mh_009`
still asserts a false negative, the contract change will be reverted and the failed fix
reported plainly.

## Measured outcome

The fixed cell `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_861c711def89` completed the
same 26 rows at temperature 0, top-p 0.95, top-k 20, seed 42, and 768 output tokens.
`mh_009` answered correctly: the invoice “exceeds” the 1099 amount and the answer gives
both `$14,549.70` and `$9,800.00`.

The preregistered conjunction nevertheless failed. Five rows that passed the committed
strict scorer stopped passing: `ag_001`, `ag_002`, `ag_011`, `ag_012`, and `mh_002`.
`ag_005` exhausted the six-step agent budget and was recorded as `TOOL_ERR`. Aggregate
strict movement was 10/26 to 11/26, but that net count cannot override the paired-loss
gate and is not an adoption rationale.

| Condition | Measured result | Verdict |
|---|---|---|
| `mh_009` correct or honestly abstained | Correct comparison and both amounts | Pass |
| No committed strict pass starts failing | Five paired strict losses | **Fail** |
| 26/26 coverage and zero `TOOL_ERR` | 26/26; one budget-exhaustion `TOOL_ERR` | **Fail** |
| Tests, lint, corpus | Delivery checks recorded in `PROGRESS.md`; corpus unchanged | Delivery only |

## Consequences

**Reject the empty-result contract and restore the previous planner prompt and SQL summary.**
The implementation and its focused regression test remain visible in commit `f72c849`,
while the paired receipt and report remain as the negative result. There is no second run
or tuned wording.

The underlying correctness bug remains open: an empty SQL result is still not logically
negative evidence, but this proposed model-facing contract did not satisfy its adoption
rule. The successful `mh_009` outcome is reported as an observation, not an accuracy claim.
