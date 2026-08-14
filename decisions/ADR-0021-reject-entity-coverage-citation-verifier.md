# ADR-0021: Reject the entity-coverage citation verifier

2026-08-14 · Status: **accepted** · Applies ADR-0020's preregistered rule

## Context

ADR-0020 preregistered one deterministic support-aware citation check after the
rejected Phase 19 prompt exposed a concrete faithfulness defect. The old verifier
confirms that quoted snippets occur in retrieved chunks but does not confirm that those
snippets support every entity named in the answer. The proposed rule extracted
capitalised entity spans from `answer_text` and required each one to occur in the
surviving citation snippets or the question. Amounts, dates, and numeric quantities
remained out of scope under `numeric_verify`.

Commit `8348e7b` implemented that fixed extractor, committed stoplist, question
threading, and whole-answer downgrade. Before any live generation, commit `c7831ab`
added the zero-generation replay and its source-hashed receipt. The replay read 13
committed Phase 18 `B_hybrid` answer files, 80 rows each, for 1,040 stored answers.

The rule predicted 96 additional downgrades. Of those, 28 row-manifest pairs currently
pass both the stored judge verdict and strict scorer, so they are false positives under
ADR-0020's binding definition. They span seven example ids:

| Example | Retracted judge+strict passes | Unsupported entities reported |
|---|---:|---|
| `cp_004` | 11 | `Cedar Grove Media` |
| `cp_005` | 11 | `Nimbus Analytics LLC` |
| `ag_001` | 1 | `Halcyon Retail Group`, `Cedar Grove Media` |
| `ag_013` | 2 | `Cedar Grove Media`, `Halcyon Retail Group` |
| `ag_014` | 1 | `Nimbus Analytics LLC` |
| `gb_003` | 1 | `Larkspur Lane`, `Astoria`, `NY` |
| `mh_007` | 1 | `Therefore` |

The receipt enumerates every source run and row rather than collapsing repeated answers
into seven unique ids. In particular, the two cross-persona rows recur across eleven
different model or decoding receipts each.

Gate 2 passed: the rejected prompt candidate's `gs_005` row was downgraded. The rule
reported `Verizon Wireless`, `CVS Pharmacy`, `Blue Bottle Coffee`, `Con Edison`, and
`Whole Foods Market` as absent from the surviving snippets and question. As
preregistered, this is a contaminated sanity check, not generalisation evidence, and it
cannot override gate 1.

## Options

**Adopt because the demonstrated fabrication was caught.** Rejected. ADR-0020 made zero
retractions of judge-and-strict passing answers the binding condition. Shipping after 28
such retractions would change the rule after observing its result.

**Tune the stoplist or extractor to rescue the retracted rows.** Prohibited. The replay
population has now revealed the specific generic token and entity patterns that fail.
Adding exceptions for them would be fitting on the evaluation population rather than a
preregistered test.

**Run the live cell for additional evidence.** Prohibited after gate 1 fails. The replay
is both cheaper and binding; a live run cannot rescue the candidate and would spend
local compute without decision value.

**Reject the product guard and retain the replay machinery.** Chosen. Restore the
shipping verifier exactly, preserve the unchanged extractor as diagnostic code, and keep
the source-hashed negative result reproducible.

## Decision

**Reject the entity-coverage citation verifier.** ADR-0020 gate 1 failed with 28
retracted judge-and-strict passes across 1,040 replayed rows. Gate 2 passed, but adoption
required every gate.

No live 80-row cell was run, and `make verify-track-a` was not run because ADR-0020
ordered both after replay gates 1–2. The fixed stoplist and extractor were not changed
after the receipt existed.

The product `verify_citations` path is restored to its prior behavior: it verifies
surviving snippets and downgrades only when no citation survives. Question threading and
the entity-support downgrade are removed. The unchanged extractor lives only in
`vaultledger/guardrails/support.py` for the replay and its tests.

## Acceptance-rule accounting

| ADR-0020 condition | Measured result | Verdict |
|---|---|---|
| Zero judge+strict passing rows retracted across replay | 28 row-manifest pairs retracted | **Fail** |
| Candidate `gs_005` downgraded | Downgraded | Pass |
| Live safety, guardrail, coverage, and `TOOL_ERR` gates | Not run; gate 1 required stop | Not reached |
| Tests, lint, Track-A, CI, corpus | Delivery checks recorded in PROGRESS; Track-A not reached | Delivery only |

## Consequences

The demonstrated support defect remains open. Verbatim citation existence is not
entailment, and a technically valid citation can still sit behind an unsupported entity.

**The 28 retractions have two distinct causes, and they should not be read as one.**
Twenty-seven are the structural finding: the answer names a real entity — `Cedar Grove
Media`, `Nimbus Analytics LLC`, `Halcyon Retail Group`, `Larkspur Lane`/`Astoria`/`NY` —
that is correct and simply does not occur in the *selected* snippets. Citation selection
is not exhaustive, so requiring every answer entity to appear in the small surviving set
is too blunt a rule. That is the result.

Exactly one retraction, `mh_007`, is a different thing: the extractor treated the
discourse word `Therefore` as an entity. The sentence-initial exclusion ADR-0020
specified is implemented and functioning; `therefore` is simply absent from
`_SENTENCE_INITIAL_COMMON_WORDS`. That is a one-word list gap, not evidence about the
approach, and it is left unfixed because ADR-0020 forbids touching the extractor after
the receipt exists.

The rejection does not depend on the distinction: 27 still fails a zero-tolerance gate.
It is recorded so a future reader neither concludes the approach is hopeless on the
strength of a stoplist omission, nor imagines that completing the stoplist addresses more
than one row of twenty-eight.

Note also that the 28 are row-manifest pairs spanning seven unique example ids, and that
22 of them are two cross-persona rows recurring across eleven receipts each. The breadth
of the replay amplifies a small number of distinct failures; seven unique ids still fails
the gate.

This result must not be reframed as an abstention-quality failure. Additional abstentions
were expected and were not an adoption criterion. The failure is specifically the 28
retractions of rows already passing both preregistered correctness signals.

Because no verifier behavior is adopted, Phase 18's model comparison, decoding null,
abstention metrics, and citation metrics continue to describe the shipped product. No
reader-facing matrix is invalidated. Phase 19 returns to its inherited comparison and
portfolio work rather than tuning this rule on the replay population.

## Evidence

- `receipts/support_coverage_replay.json` — 13 source files, 1,040 rows, 96 predicted
  downgrades, all 28 false-positive row-manifest pairs, gate 2, and SHA-256 hashes of
  every source answers file and manifest.
- `8348e7b` — isolated verifier implementation and tests, before replay.
- `c7831ab` — replay implementation, Make target, tests, and measured receipt.
- ADR-0020 — fixed semantics, ordering, and adoption rule.
