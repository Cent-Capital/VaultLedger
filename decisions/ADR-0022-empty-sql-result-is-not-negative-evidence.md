# ADR-0022: An empty SQL result is not negative evidence

2026-08-15 · Status: **accepted for measurement**

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
