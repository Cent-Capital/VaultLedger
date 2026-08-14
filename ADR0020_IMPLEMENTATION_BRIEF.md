# ADR-0020 implementation — support-aware citation verification

Opened 2026-08-14 · For Codex · Implements ADR-0020 · Follows `c7f7b32`

Read `decisions/ADR-0020-support-aware-citation-verification.md` first. The semantics,
the scope boundary, and the adoption rule are fixed there **before** any code or
measurement exists. Do not re-derive them and do not adjust a threshold after seeing a
number.

**Entry state (verify, do not assume):** `main` at `c7f7b32`, pushed, CI green.
`make test` 204 passed, `make lint` clean, corpus hash
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`. Working tree clean.

**The cheap gates come first.** Gate 1 is measurable by replay with zero generation
calls. If it fails, stop and report — do not spend the live cell.

---

## 1. Thread the question into the verifier

`verify_citations(draft, hits, *, min_snippet_chars)` in
`vaultledger/generate/reliable.py` does not currently receive the question, and ADR-0020's
support set includes question text. Add a `question: str` parameter and update the call
sites in `answer_question_reliable` and the agentic path. This is the only signature
change required.

## 2. The entity extractor

New, deterministic, committed alongside a stoplist. Suggested home: a small module or a
private helper block in `reliable.py` next to `_normalize`, which already does the
whitespace-and-lowercase normalisation you should reuse.

- Claim units are **maximal spans of capitalised tokens**.
- Exclude a span at sentence-initial position when its only token is a common word.
- Exclude a committed stoplist: months, weekdays, and the fixed vocabulary of
  `ABSTAIN_SENTENCE`.
- **Amounts, dates and numeric quantities are out of scope.** They belong to
  `numeric_verify`. An amount-coverage rule would retract every correct aggregation
  answer, which is why ADR-0020 excludes them.
- Match case-insensitively after normalisation.

The stoplist and extractor are committed with the implementation and **are not tuned
after results exist**.

## 3. The check itself

In `verify_citations`, after the existing `asserts_facts and not surviving` downgrade
block and before the final `return VerifyResult(citations=surviving, events=events)`:

- Applies only when `asserts_facts` is true and citations survived.
- Support set = concatenated `surviving` snippet text **+ the question text**.
- If any extracted entity from `draft.answer_text` is absent from the support set,
  emit a `GuardrailEvent(stage="output", guard="citation_verify",
  action="downgrade_to_abstain", ...)` whose `details` names the unsupported entities,
  and return `VerifyResult(citations=[], events=events, downgrade_to_abstain=True)`.
- Match the existing `[CITE_FAIL]` detail convention so downstream taxonomy handling is
  unchanged.

Answers cannot be partially retracted; the whole answer downgrades, as the existing
no-surviving-citation path already does.

## 4. The replay — primary measurement, zero generation

New script, phase-neutral name (`scripts/support_coverage_replay.py`), plus a
`support-coverage-replay` make target. It reads only `answer_text` and the surviving
`citations` from committed answers files, so it needs no model.

**Population:** every committed `B_hybrid` `*_answers.json` — the six Phase 18 model
cells, the six decoding-sweep cells, the frozen baseline
`…c64ee5ca952f`, and the rejected candidate `…d5c5f885d0c9`.

**Receipt** (`receipts/support_coverage_replay.json`), following the pattern in
`scripts/phase19_abstention_audit.py`: git sha, config hash, and a SHA-256 of every
source answers file, so the replay is provably tied to the artifacts it read. Per
manifest, record rows downgraded and, for each, its current judge and strict status.
Include an `interpretation_boundary` string.

Reuse the audit script's fail-loud habits: duplicate or missing rows raise rather than
silently skew a count.

## 5. Apply ADR-0020's rule — in this order

**Gate 1 — zero false positives (binding).** The rule downgrades **no** row that
currently passes both the judge and the strict scorer, anywhere in the replay
population. If any such row is downgraded: **stop.** Report which correct answers were
retracted, do not run the live cell, and do not tune the stoplist or extractor to rescue
them — that is fitting on the evaluation population.

**Gate 2 — catches the demonstrated fabrication.** The `gs_005` row of
`…d5c5f885d0c9` is downgraded. This is a sanity check, not evidence of generalisation;
ADR-0020 says so explicitly and the write-up must repeat it.

**Gate 3 — live cell.** Only if gates 1 and 2 pass. One full 80-row
`ollama/qwen3:8b` / `B_hybrid` / guardrails-on cell:

```make
support-coverage-cell:  ## ADR-0020: one live cell with support-aware verification
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/adr0020_support_matrix.md \
		--frontier reports/adr0020_support_frontier.svg
```

Requires: 10/10 unanswerable still abstain, the poisoned-document row still handled
correctly, the full Phase 13 guardrail gate green, coverage 80/80, `TOOL_ERR` zero.
~15 minutes on an idle machine.

**Gate 4 — delivery.** `make test`, `make lint`, `make verify-track-a`, CI green, corpus
hash unchanged.

**Judge pass count and strict match count are not adoption criteria.** Abstentions are
expected to rise and a rise is not a failure. Do not reuse ADR-0018's "fewer abstentions"
framing anywhere in the write-up.

## 6. Tests

- An answer naming an entity absent from both snippets and question downgrades.
- An answer whose entities all appear in surviving snippets does not.
- An entity present only in the **question** does not downgrade.
- An aggregation-style answer stating a computed total absent from every snippet does
  **not** downgrade — this is the amount-scope boundary and it is the regression most
  likely to be broken by a future "improvement".
- Stoplist behaviour: a sentence-initial common word is not treated as an entity.
- The existing `verify_citations` behaviour is unchanged for every current test.

Each of these should fail against an implementation that ignores it. A test that passes
either way is not protecting anything.

## 7. If a gate fails

**Revert the verifier change from the product path**, exactly as the Phase 19 candidate
was reverted. Keep the replay script, the receipt, the tests, and a written finding — a
negative result is recorded, not discarded. Do not carry a guard that failed its own
preregistered gate into the shipped product.

## 8. Deliverables

- Commit 1: extractor, verifier change, signature threading, tests. No run artifacts.
- Commit 2: replay script, make target, replay receipt, and the gate-1/gate-2 result.
- Commit 3 (only if gates 1–2 passed): the live cell's manifest, answers, generated
  report and frontier.
- **ADR-0021** recording adoption or rejection against ADR-0020's rule, citing the
  replay receipt and the manifest ids.
- A PROGRESS entry with the measured numbers and their boundaries.
- Push, then check CI with `gh run list` — do not infer it.

## Boundaries

- No paid APIs; `$0.00` means unpriced, not free.
- No loosening of any existing guard. This change only tightens.
- No stoplist or extractor tuning after results exist.
- No hand-edited generated report or chart.
- No changes to Phase 15's recorded numbers, Phase 17's waiver status, or the frozen
  Phase 18 baseline and candidate manifests.
- If adopted, state plainly which reader-facing metrics move. ADR-0020's gate 1
  guarantees judge and strict counts cannot fall, so the ADR-0016 model claim and the
  ADR-0017 decoding null survive unchanged; abstention and citation metrics may not.
