# Fix brief — an empty SQL result is not a negative finding

Opened 2026-08-15 · For Codex · Small, contained, ~1 hour · Follows `7ded26c`

This is a **correctness bug fix, not an improvement experiment.** It is not expected to
raise any accuracy metric, and the write-up must not claim it does. What it removes is a
class of confidently wrong output.

---

## The bug

`SqlResult.summary()` in `vaultledger/retrieve/agentic.py:130-141` serialises an empty
result as `{"columns":[...],"rows":[],"provenance_doc_ids":[],"truncated":false}` with no
interpretation attached. The planner fills that gap by treating zero rows as evidence that
the fact is false.

Two rows in the committed Phase 11 agentic receipt
(`phase11_ollama_qwen3_8b_d_agentic_4c9522233d68`) show it:

**`mh_003`** — one SQL step, a self-join on `form_1099_boxes`, `"rows":[]`, then `finish`:

> "I couldn't find that in your documents."

**`mh_009`** — SQL returns `"rows":[]`, a retrieve step, SQL returns `"rows":[]` again, then:

> "The invoice DAVID-HALCYON-005 **did not exceed** David's Halcyon 1099 amount."

The invoice was **$14,549.70**; the 1099 was **$9,800.00**. It did exceed. The system stated
a false comparison on the strength of an empty result set.

`mh_003` degraded to an honest refusal, which is tolerable. `mh_009` asserted a falsehood,
which is not — it is precisely the failure this product exists to prevent.

**Root cause is a schema gap:** `invoices` carries only `vendor` and `forms_1099` carries
`payer_name`/`recipient_name`, so there is no join path between them except
`documents.doc_id`. The comparison genuinely cannot be one query. The planner tried anyway
and got silence. Fixing the schema is out of scope here; fixing the *interpretation of
silence* is not.

## The change

In `SqlResult.summary()`, when `rows` is empty, add two explicit fields:

```
"result": "NO_ROWS_RETURNED",
"interpretation": "An empty result means this query matched nothing. It is NOT evidence
that the fact is false, absent, or smaller. Do not state a negative or comparative
conclusion from an empty result. Re-query more simply, split a join into separate lookups,
or use retrieve."
```

**Do not raise `AgentToolError` on empty results.** Some queries legitimately return zero
rows — "are there duplicate charges" answers itself with an empty set. The contract must
mark empty results as *uninformative*, not as failures.

Mirror the same instruction in the planner's tool description so the rule is present before
the model sees its first empty result, not only after.

**Nothing else in this commit.** No schema change, no query templates, no retrieval change,
no guard change.

## Write the rule down before running

Short ADR (ADR-0022), committed **before** the re-run. Adopt if all hold:

1. `mh_009` no longer asserts a negative or comparative conclusion from an empty result —
   it either answers correctly or abstains honestly.
2. No row that currently passes the strict scorer starts failing.
3. 26/26 coverage, zero `TOOL_ERR`.
4. `make test`, `make lint` green; corpus hash unchanged.

**Accuracy is explicitly not an adoption criterion.** The expected outcome is that a false
assertion becomes an honest abstention, which does not score better. If strict or judge
counts happen to move, report it as an observation, not as the justification.

## Measure it

Re-run the agentic path over its 26 aggregation/multi-hop rows against the same model and
decoding profile as the committed receipt, so the comparison is paired:

```make
agentic-empty-result-check:  ## ADR-0022: re-run D's 26 rows after the tool-contract fix
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--variants D_agentic --limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/adr0022_agentic_matrix.md
```

Roughly 10 minutes. In the write-up, quote `mh_009`'s before and after answer text verbatim
side by side — that pair *is* the result, more than any count.

Also report: how many of the 26 rows produced an empty SQL result at any step, before and
after, and what the planner did next in each case.

## Deliverables

- Commit 1: ADR-0022 with the rule, before any re-run.
- Commit 2: the tool-contract change plus a test asserting an empty `SqlResult` summary
  contains `NO_ROWS_RETURNED` and the interpretation string, and that a non-empty result is
  unchanged.
- Commit 3: the re-run manifest, report, and a PROGRESS entry.
- Push, then check CI with `gh run list` — do not infer it.

## Boundaries

- No schema changes, no person dimension, no query templates — that is the deferred
  Phase 20 work and it needs a fresh corpus.
- Do not touch the frozen Phase 18 baseline or candidate manifests.
- Do not describe this as an accuracy improvement.
- If `mh_009` still asserts a false negative after the change, report that plainly and
  revert. A failed fix is a finding.
