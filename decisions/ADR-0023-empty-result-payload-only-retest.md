# ADR-0023: Retest the empty-result contract, payload only, against a same-code baseline

2026-08-15 · Status: **accepted (preregistration)** · Supersedes ADR-0022's rejection as
*made on confounded evidence* · No result is claimed here

## Context

ADR-0022 rejected the empty-result contract because five rows that passed the committed
strict scorer stopped passing. A review of the two manifests shows that comparison could not
isolate the contract:

| | baseline `phase11_…4c9522233d68` | ADR-0022 run `matrix_…861c711def89` |
|---|---|---|
| git sha | `c570000b` | `f72c849b` |
| config hash | `22e0086c` | `f8f9b3e4` |
| decoding block | **absent** | native `ollama_chat`, `top_k=20`, `num_ctx=8192` |

**Three variables moved between the arms**, not one: the empty-result payload, an edit to
the always-present SQL tool description, and the entire ADR-0015 transport correction —
which ADR-0015 explicitly declined to describe as behaviour-neutral.

Two facts survive that confound and both are worth keeping:

- **`mh_009` was fixed.** Before: *"did not exceed David's Halcyon 1099 amount."* After:
  *"$14,549.70, which exceeds David's Halcyon 1099 amount of $9,800.00."* Correct direction,
  both figures.
- **All five losing rows never produced an empty SQL result**, before or after. The payload
  change cannot have reached them. Seven rows produced empty results in each arm.

What the losses *were* caused by remains undetermined — the tool-description edit and the
transport change are both always-present and cannot be separated by the existing receipts.
`D_agentic` has never been run on the post-ADR-0015 stack without the contract change, so no
clean baseline exists.

ADR-0022's verdict is therefore not overturned on its merits; it is set aside as untestable
on the evidence gathered.

## Decision — what changes, and what deliberately does not

**Ship the payload change only.** When `SqlResult.summary()` in
`vaultledger/retrieve/agentic.py` serialises zero rows, add:

```json
{
  "result": "NO_ROWS_RETURNED",
  "interpretation": "An empty result means this query matched nothing. It is NOT evidence that the fact is false, absent, or smaller. Do not state a negative or comparative conclusion from an empty result. Re-query more simply, split a join into separate lookups, or use retrieve."
}
```

**Do not modify the SQL tool description, the planner prompt, or anything else.** ADR-0022
mirrored this instruction into the always-present tool description, which rewrote the
agent's policy on all 26 rows rather than the 7 that hit the condition. That was the error
being corrected here. Empty results still do not raise `AgentToolError`; non-empty summaries
are unchanged.

Confining the intervention to rows meeting the condition is a general design rule, not a
pattern fitted to which rows happened to break. That distinction is what makes this retest
legitimate rather than a second bite.

## Measurement — baseline first, then one variable

Two runs of `D_agentic` over its 26 aggregation and multi-hop rows, `ollama/qwen3:8b`,
guardrails on, current decoding profile:

1. **Baseline at current `HEAD` with no code change.** This is the artifact that does not
   exist and without which nothing here is interpretable.
2. **The payload change**, run identically.

Compare run 2 against run 1 — same code, same transport, same decoding, one variable. The
Phase 11 receipt is **not** the comparator and must not be used as one.

## Preregistered adoption rule

Adopt only if **all** hold, comparing run 2 against run 1:

1. `mh_009` does not draw a negative or comparative conclusion from an empty result — it
   answers correctly or abstains honestly.
2. **No row passing the run-1 strict scorer starts failing.**
3. Coverage 26/26 with zero `TOOL_ERR` in run 2.
4. `make test`, `make lint` green; synthetic corpus hash unchanged.

**Accuracy is not an adoption criterion.** Converting a false assertion into an honest
abstention may leave counts flat or lower. Any strict or judge movement is an observation.

## Reported diagnostic — the containment prediction

The reasoning above predicts something falsifiable: **the 19 rows that produce no empty SQL
result should be behaviourally identical between runs 1 and 2**, because their prompts are
byte-identical and decoding is greedy.

Report, do not gate on it: how many of those 19 rows differ between the two runs on
`strict_match`, on `abstained`, and on `answer_text` byte-equality. The prediction is zero.
A non-zero count means containment failed and the diagnosis in this ADR is wrong — record
that plainly rather than explaining it away.

Also report, both runs: rows producing at least one empty SQL result, and the planner's next
action after each.

## Consequences

If adopted, an empty database result can no longer be read by the planner as proof a fact is
false — the specific defect that made `mh_009` assert a false financial comparison. The
underlying schema gap that produced the empty joins is untouched and remains deferred
Phase 20 work.

If rejected, revert the payload change from the product path, keep both receipts and the
implementation commit as the negative result, and stop. **There is no third attempt.**
Two rejections would be sufficient evidence that model-facing contract wording is the wrong
lever for this defect, and the honest conclusion would be that it needs the schema fix
instead.

## Evidence

- `phase11_ollama_qwen3_8b_d_agentic_4c9522233d68` — the confounded pre-ADR-0015 baseline,
  retained as history and explicitly not the comparator.
- `matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_861c711def89` — the ADR-0022 run.
- ADR-0022 — the rejection this supersedes, and the source of the `mh_009` before/after text.
- ADR-0015 — the transport change that is the third uncontrolled variable.
