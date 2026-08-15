# ADR-0023 retest — payload only, baseline first

Opened 2026-08-15 · For Codex · ~1.5 hours including two 10-minute runs

Read `decisions/ADR-0023-empty-result-payload-only-retest.md` first. The change, the rule
and the diagnostic are fixed there before any code or measurement.

**Why this is not a second bite at ADR-0022.** That comparison moved three variables at once
— the payload, the tool description, and the whole ADR-0015 transport — so it could not test
the contract. Its rejection is set aside as untestable, not overturned. This retest changes
one variable against a baseline built on the same code.

---

## 1. Baseline run — do this before touching any code

`D_agentic` has never run on the post-ADR-0015 stack. Without this artifact nothing else is
interpretable.

```make
agentic-baseline:  ## ADR-0023 run 1: D_agentic at current HEAD, no code change
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--variants D_agentic --limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/adr0023_agentic_baseline.md
```

Commit the manifest and answers before writing any implementation. That ordering is the
point: the baseline must not be produced after seeing the candidate.

## 2. The change — one function, nothing else

`SqlResult.summary()` in `vaultledger/retrieve/agentic.py:130-141`. When `rows` is empty, add
the two fields exactly as written in ADR-0023.

**Do not touch the SQL tool description. Do not touch the planner prompt.** Commit `f72c849`
did both; that is the specific thing being corrected. If you find yourself editing any string
the model sees on a row that has *no* empty result, stop — that is out of scope by
construction.

Empty results still return normally, never `AgentToolError`. Non-empty summaries byte-identical.

Test: an empty `SqlResult.summary()` contains `NO_ROWS_RETURNED` and the interpretation
string; a non-empty summary is unchanged from current behaviour.

## 3. Candidate run

Same command, new report path (`reports/adr0023_agentic_candidate.md`). Same model, guard
arm and decoding as run 1.

## 4. Apply the rule, comparing run 2 against run 1 only

The Phase 11 receipt is **not** the comparator. Using it reintroduces the confound.

1. `mh_009` no longer concludes a negative or comparison from an empty result.
2. No row passing run 1's strict scorer starts failing.
3. 26/26 coverage, zero `TOOL_ERR`.
4. `make test`, `make lint`, corpus hash.

Accuracy is not a criterion. Report movement as an observation.

## 5. Report the containment diagnostic

The ADR predicts the 19 rows with no empty SQL result are behaviourally identical between
runs, since their prompts are unchanged and decoding is greedy.

Report counts, don't gate on them: of those 19, how many differ on `strict_match`, on
`abstained`, and on `answer_text` byte-equality. **Prediction is zero.** If it isn't zero,
say so plainly — that falsifies the ADR's diagnosis and is more valuable than a pass.

Quote `mh_009`'s answer text from both runs verbatim, side by side.

## 6. Outcome

**Adopted** — ADR-0024 records it, the payload ships, PROGRESS entry with both manifest ids.

**Rejected** — revert the payload from the product path exactly as `dbe8095` did, keep both
receipts and the implementation commit as the negative result, and **stop. No third attempt.**
Two clean rejections would mean contract wording is the wrong lever and the schema fix is the
real answer.

Either way, add both runs to `REJECTED_CODE_SHAS` in `vaultledger/evals/failure_pareto.py` if
rejected, following the pattern in `1a641b4`, so a non-shipping run never describes the
product's history.

## Boundaries

- No schema change, no query templates, no person dimension — deferred Phase 20.
- No edit to any always-present model-facing string.
- No tuned wording after seeing the result.
- Don't touch the frozen Phase 18 baseline or the Phase 11 D receipt.
- Push, then check CI with `gh run list` — do not infer it.
