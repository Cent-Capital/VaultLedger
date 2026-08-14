# ADR-0020: Preregister support-aware citation verification (entity coverage)

2026-08-14 · Status: **accepted (preregistration)** · Amends ADR-0019's "next work"
statement · No result is claimed here

## Context

`verify_citations` checks that a quoted snippet **exists verbatim** in a retrieved chunk.
It never checks that the snippet **supports** the answer, and abstention fires only when
*zero* citations survive. Both limitations have been named in every brief since Phase 18
as abstract known-open defects.

Phase 19 turned the first one into a demonstrated harm. On `gs_005` the evidence-first
candidate answered:

> The recurring merchants that appear on bank statements are: Halcyon Retail Group,
> Netflix, Verizon Wireless, **CVS Pharmacy**, Blue Bottle Coffee, Con Edison, and
> Whole Foods Market.

Two citations survived verification because their snippets were genuinely verbatim. The
string `CVS` appears in **no** surviving snippet. A fabricated merchant reached the
output with a passing citation check. The judge caught it; the guard stack did not.

**Sequencing forces this now rather than after the portfolio.** ADR-0019 said the next
work was Phase 19's inherited comparison and portfolio scope. That ordering is wrong for
this change: a verifier that alters answer behaviour makes Phase 18's model and decoding
matrices historical evidence about the old verifier — the same invalidation ADR-0018
anticipated for the prompt. Freezing the portfolio first and changing the verifier second
would invalidate the portfolio immediately. This ADR therefore inserts one bounded
verifier experiment ahead of the portfolio work. It is not a second abstention tweak:
ADR-0019 forbade another *prompt* candidate, and this tightens a guard rather than
loosening one.

**The 80 golden rows are contaminated for this question.** `gs_005` motivated the change
and has already informed the Phase 19 hypothesis, candidate, and rejection. That is
handled in the measurement design below, not waved away.

## Options

**Deterministic entity coverage (chosen).** Every named entity asserted in `answer_text`
must appear in the surviving cited snippets or in the question. Local, deterministic, no
new dependency, no extra model call. Catches `gs_005` exactly. It will not catch a wrong
*relationship* between facts that are each individually present — which is what
`mh_008` and `mh_009` got wrong — and that limitation is accepted, not hidden.

**Local NLI / entailment cross-encoder.** Better semantics, catches relational errors.
Rejected for this pass: new dependency and model weights, per-answer latency, and a
second learned component whose own accuracy would need validating before it could gate
a product answer.

**LLM entailment call at answer time.** Best semantics. Rejected: it adds a generation
call to every answer, and it would gate the product on a judge the repo already labels
weak evidence at ≥83% accuracy.

**Defer past the portfolio.** Rejected on the sequencing argument above.

## Decision — the rule, fixed before any measurement

Add a support check that runs **after** existing snippet verification, on answers that
did not abstain and have non-empty text.

**Claim units are named entities only.** Amounts, dates and numeric quantities are
explicitly **out of scope** and remain the responsibility of `numeric_verify`. This is
deliberate: aggregation answers legitimately state computed totals that appear in no
snippet, and an amount-coverage rule would downgrade every correct aggregation row.

**Support set** = the concatenated text of surviving citations **plus the question
text**. Question terms count as supported; a user asking about "Marcus Chen" may have
that name echoed back without it appearing in a snippet.

**Entity extraction** is deterministic: maximal spans of capitalised tokens, excluding
sentence-initial position when the token is a common word, with a committed stoplist
(months, weekdays, and the fixed vocabulary of the abstain sentence). Matching is
case-insensitive after whitespace normalisation. The stoplist and the extractor are
committed with the implementation and are not tuned after results exist.

**Action on failure:** downgrade the whole answer to an honest abstention and emit a
`citation_verify` guardrail event with a new detail string naming the unsupported
entities. Answers cannot be partially retracted, and this matches the existing
`CITE_FAIL` downgrade behaviour.

### Measurement design: replay first, live second

The check reads only `answer_text` and the surviving `citations`, both of which are
stored in every committed answers file. It is therefore **replayable deterministically
over already-committed manifests with zero generation calls.** That is the primary
measurement, and it substantially defuses the contamination problem: the rule is fixed
here, then applied to roughly a thousand rows that were generated before it existed.

Replay population: every committed `B_hybrid` answers file — the six Phase 18 model
cells, the six decoding-sweep cells, the frozen baseline, and the rejected Phase 19
candidate. Report per manifest: rows downgraded, and the current judge and strict status
of each downgraded row.

### Preregistered adoption rule

Adopt only if **all** hold:

1. **Zero false positives.** The rule downgrades **no** row that currently passes both
   the LLM judge and the strict scorer, across the entire replay population. This is the
   binding condition; a guard that retracts correct answers is worse than the defect.
2. It downgrades the `gs_005` candidate row, the one demonstrated fabrication.
3. On a live full 80-row `qwen3:8b` / `B_hybrid` / guardrails-on cell: 10/10 unanswerable
   still abstain, the poisoned-document row is still handled correctly, the full Phase 13
   guardrail gate is green, coverage is 80/80 and `TOOL_ERR` is zero.
4. `make test`, `make lint`, `make verify-track-a`, CI green; corpus hash unchanged.

Judge pass count and strict match count are **not** adoption criteria and are **not**
expected to improve. Condition 1 already forbids losing a passing row; this change is a
faithfulness fix, not a quality optimisation. Abstentions are expected to rise, and a
rise is not a failure — ADR-0018's "fewer abstentions" framing does not apply here and
must not be reused.

If condition 1 fails, report which correct rows were retracted and stop. Do not tune the
stoplist or the extractor to rescue them on this population; that is fitting.

## Consequences

If adopted, an unsupported entity can no longer reach the user behind a technically
verbatim citation. The known relational-error gap remains open and is the natural
candidate for a later entailment pass.

Because condition 1 requires that no currently-passing row is downgraded, the Phase 18
model ranking and decoding null are preserved by construction: judge and strict counts
cannot fall. Abstention and citation metrics can move, so any reader-facing claim built
on those specific metrics must be rerun or narrowed. ADR-0016's "measured against five
alternatives; none beat it" and ADR-0017's decoding null survive unchanged.

The replay is evidence about answers produced under the old verifier. It predicts which
existing answers the rule would retract; it does not predict how a model behaves when the
guard is live, which is why condition 3 requires one live cell.

Contamination is reduced but not eliminated: `gs_005` remains a row that motivated the
rule and is named in condition 2. Condition 2 is therefore a sanity check, not evidence
of generalisation. The generalisation claim rests on condition 1 across the full replay
population.

## Evidence

- Defect demonstrated at `gs_005` in
  `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9` (the rejected Phase 19
  candidate): `CVS Pharmacy` in `answer_text`, absent from both surviving snippets.
- Current behaviour: `verify_citations` in `vaultledger/generate/reliable.py`, which
  documents the snippet as "the authoritative signal" and downgrades only when nothing
  survives.
- ADR-0019 — rejection of the evidence-first candidate, and the `FALSE_ABSTAIN`-to-
  `INCORRECT` conversions that exposed this row.
- Replay population: all committed `B_hybrid` `*_answers.json` files as of `f0c0348`.

No implementation exists at the time of writing and no result is claimed.
