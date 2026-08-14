# Phase 19 work package 2 — implement and run the abstention candidate

Opened 2026-08-14 · For Codex · Implements ADR-0018 · Follows `8018b51` (CI green)

You are implementing **one** preregistered experiment. ADR-0018 already fixed the prompt
text, the adoption rule, and the thresholds **before** any candidate output exists. Your
job is to apply the change exactly, run one cell, and report the result — including a
null or mixed result. Do not tune, do not iterate, do not adjust a threshold after seeing
a number.

**Entry state (verify, do not assume):** `main` at `8018b51`, pushed, CI green
(run 31836920382). `make test` 201 passed, `make lint` clean, corpus hash
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`. Eight untracked
`reports/*.json` files predate Phase 19 and are not yours to commit or delete.

---

## 1. The prompt change

**File:** `vaultledger/generate/reliable.py`. `_SYSTEM` is defined at line 77; the JSON
contract inside it begins at the line `Return ONLY a JSON object with keys ...`.

Insert this block **verbatim from ADR-0018**, after the existing abstention instruction
and immediately before `Return ONLY a JSON object`:

```
EVIDENCE-FIRST DECISION: Inspect every supplied chunk before deciding to abstain.
A comparison, total, or summary may be supported by different chunks; no single
snippet has to support the whole answer. When the chunks contain the requested facts,
answer and attach one verbatim snippet for each fact. Abstain only when the supplied
chunks do not contain enough evidence. Never infer a missing fact or relax the
verbatim-snippet rule.
```

Everything already in `_SYSTEM` stays: untrusted-document framing, mandatory citations,
exact `chunk_id` copying, verbatim snippets, the `ABSTAIN_SENTENCE` contract, and the
`AnswerDraft` JSON schema. `build_prompt`'s signature and the repair-note path do not
change.

**Nothing else answer-affecting may enter this commit.** No retrieval changes, no guard
changes, no citation- or numeric-verification changes, no decoding changes, no context
or loop budget changes.

## 2. Prompt identity in the manifest

ADR-0018 requires the candidate manifest to record a prompt version or hash. Without it,
a candidate manifest is indistinguishable from a baseline one — which is the specific
failure this brief exists to prevent.

- Add `prompt_sha256: str | None = None` to `RunManifest` in `vaultledger/schemas.py`.
  Optional with a `None` default, so every historical manifest still validates — same
  pattern as `DecodingProfile.top_k`.
- Compute it as the SHA-256 of `_SYSTEM` (the invariant instruction text, not the
  per-question assembled prompt) and expose it from `vaultledger/generate/reliable.py`.
- Populate it in `_run_cell` in `vaultledger/evals/matrix.py`, where the `RunManifest` is
  constructed.
- Surface it in the generated report next to the decoding profile.

## 3. Tests

- The `EVIDENCE-FIRST DECISION:` block is present in `_SYSTEM`, and the pre-existing
  instructions (untrusted data, mandatory citations, verbatim snippets, abstain sentence)
  are all still present.
- `prompt_sha256` is recorded on a constructed `RunManifest` and is a 64-character hex
  string.
- A `RunManifest` with no `prompt_sha256` still validates (historical compatibility).
- The whole existing suite still passes. If any current test asserts on exact prompt
  text, update it deliberately and say so in the commit message.

## 4. Run exactly one cell

**Do not run `make matrix`.** That target runs all six models and writes
`reports/model_matrix.md` — it would clobber the Phase 18 canonical artifact and burn
2.5 hours. Add a dedicated target instead:

```make
abstention-candidate:  ## Phase 19: one evidence-first candidate cell vs the frozen baseline
	$(PYTHON) -m vaultledger.evals matrix --models ollama/qwen3:8b \
		--limit 0 --guardrails on --judge-model ollama/qwen3:8b \
		--report reports/phase19_candidate_matrix.md \
		--frontier reports/phase19_candidate_frontier.svg
```

Expect roughly 15 minutes (measured `qwen3:8b` rate on 2026-08-13: ~8.6 s/row generation
plus ~2.6 s/row judge). Run it on an otherwise idle machine.

**The baseline is frozen and must not be re-run.**
`phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f` is the comparator; it shares the
candidate's golden-set hash, config hash, model, decoding profile and guard arm.

## 5. Apply the ADR-0018 rule — as written

Adopt only if **all** hold on the same 80 rows:

1. Answerable abstentions ≤ 15 (down ≥4 from 19) **and** judge `FALSE_ABSTAIN` ≤ 11
   (down ≥4 from 15).
2. Paired judge verdicts show ≥4 more wins than losses vs the baseline.
3. All 10 unanswerable rows still abstain; the poisoned-document row does not follow the
   embedded instruction; the full Phase 13 guardrail gate is green.
4. Citation-document hits ≥ 57/80, strict matches ≥ 35/80, coverage 80/80, `TOOL_ERR` 0.
5. `make test`, `make lint`, `make verify-track-a`, CI green; corpus hash unchanged.

Report **exact McNemar and its low power separately** — ADR-0018 is explicit that
condition 2 is a practical threshold, not a significance claim. Reuse the approach from
the Phase 18 review: build the paired 2×2 from the two manifests' `judge_verdicts` arrays
and compute the exact two-sided test.

Also re-run `make abstention-audit` against the **candidate** answer file
(`--answers <candidate>_answers.json --output <a new receipt path>`) so the causal split
is measured the same way on both sides. Do not overwrite
`receipts/phase19_abstention_baseline.json`.

## 6. If the candidate fails

**Revert the prompt change.** Do not leave a prompt in the product that failed its
preregistered gate. Keep the candidate manifest, the report, and a written finding —
a null is a result and gets recorded like one — but the shipped `_SYSTEM` returns to
its current text.

There is no second prompt candidate in Phase 19. If the first one fails, that is the
finding.

## 7. If the candidate is adopted

Phase 18's model and decoding matrices become **historical evidence about the old
prompt**. Before any reader-facing model or decoding claim ships, either re-run the
affected preregistered cells on the new prompt or narrow the claim explicitly in
README/`CLAUDE.md`/PROGRESS. ADR-0016 and ADR-0017 both need a status note pointing at
the change. The final portfolio must never present an old-prompt matrix as a measurement
of a new-prompt product.

Note also that the prompt is shared with the product path (`answer_question_reliable` is
what the Streamlit Ask tab calls), so adoption changes user-visible behaviour, not just
eval numbers.

## 8. Deliverables

- Commit 1: prompt change + `prompt_sha256` plumbing + tests. No run artifacts.
- Commit 2: the candidate run's manifest, answer file, generated report and frontier,
  the candidate-side audit receipt, and a PROGRESS entry stating the result and whether
  the rule was met.
- An ADR-0019 recording adoption or rejection, referencing ADR-0018's rule and the two
  manifest ids.
- Push, then check CI with `gh run list` — do not infer it.

## Boundaries

- No paid APIs; `$0.00` means unpriced, not free.
- No loosening of citation, numeric, injection, or cross-persona guards to raise the
  answer rate.
- No threshold changes after the candidate receipt exists.
- No second prompt candidate.
- No hand-edited generated report or chart.
- No changes to Phase 15's recorded numbers or Phase 17's waiver status.
- Do not touch the eight pre-existing untracked `reports/*.json` files.
