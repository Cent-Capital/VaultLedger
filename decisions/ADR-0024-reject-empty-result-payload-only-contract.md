# ADR-0024: Reject the empty-result payload-only contract

2026-08-15 · Status: **accepted** · Applies ADR-0023's preregistered rule

## Context

ADR-0023 set aside ADR-0022's rejection because its Phase 11 comparator predated the
ADR-0015 transport and the candidate also changed the always-present SQL tool description.
The retest first created the missing post-ADR-0015 baseline, then changed only the JSON
payload returned when SQL produced zero rows.

The two completed runs share model, config hash, 26-row population, guard arm, judge,
temperature 0, top-p 0.95, top-k 20, seed 42, 8,192-token context, 768-token output cap,
thinking-off setting, and native Ollama chat transport:

| Arm | Product git SHA | Run id |
|---|---|---|
| Baseline | `7896cae` | `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_6a82bd327b6e` |
| Payload only | `dbcfcde` | `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_a4da2769451b` |

No planner prompt, SQL tool description, schema, query template, retrieval path, guard,
or decoding setting changed between the arms.

## Result

`mh_009` satisfied the target rule in both arms by answering exactly, “I couldn't find
that in your documents.” The candidate did not draw a negative or comparative conclusion
from its empty result.

The adoption conjunction nevertheless failed twice. `mh_011` passed the baseline strict
scorer with both balances and the correct comparison, then the candidate abstained. The
candidate also recorded four budget-exhaustion `TOOL_ERR`s: `ag_003`, `mh_009`, `mh_010`,
and `mh_012`.

| ADR-0023 condition | Measured result | Verdict |
|---|---|---|
| `mh_009` correct or honestly abstained | Honest abstention, no false comparison | Pass |
| No baseline strict pass starts failing | `mh_011` stopped passing | **Fail** |
| 26/26 candidate coverage; zero `TOOL_ERR` | 26/26; four `TOOL_ERR`s | **Fail** |
| Tests, lint, corpus | Delivery checks recorded in `PROGRESS.md`; corpus unchanged | Delivery only |

Strict and numeric-exact counts were both flat at 11/26 and 11/24. Citation-document hits
and correct abstention decisions moved from 11/26 to 14/26; judge passes moved from 12/26
to 13/26. These are observations only. Accuracy was not an adoption criterion and cannot
override the paired loss or error gate.

## Containment diagnostic

ADR-0023 predicted seven empty-result rows and therefore 19 unaffected rows. The fresh
baseline falsified that denominator: both arms had the same **eight** empty-result rows,
leaving 18 unaffected rows. Across the actual 18, differences were zero for
`strict_match`, zero for `abstained`, and zero for byte-exact `answer_text`.

The payload intervention was behaviorally contained, but the preregistered population
count was wrong. This does not rescue the candidate: `mh_011` is one of the eight rows
that received the payload, and its paired regression is inside the intervention scope.

## Decision

**Reject the payload-only empty-result contract.** Restore the prior `SqlResult.summary()`
behavior and remove the candidate regression test from the shipping tree. Preserve the
baseline, candidate, implementation commit, reports, and this decision as the result.

There is no third model-facing wording attempt. ADR-0023 fixed that stop rule in advance;
two rejected contract experiments are sufficient evidence that wording is the wrong lever.
The demonstrated logical defect remains open and moves to the deferred Phase 20 schema
work, where invoices and 1099s can be compared through an explicit person relationship.

Both ADR-0023 run SHAs are excluded from the generated failure-Pareto history. The baseline
is retained as the experiment comparator and the candidate ran code the product does not
ship; neither is allowed to become an accidental product-history snapshot.

## Evidence

- Baseline report and receipt: `reports/adr0023_agentic_baseline.md` and
  `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_6a82bd327b6e`.
- Candidate report and receipt: `reports/adr0023_agentic_candidate.md` and
  `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_a4da2769451b`.
- Payload-only implementation: commit `dbcfcde`.
- Complete paired accounting and every empty-result follow-up: `PROGRESS.md`.
