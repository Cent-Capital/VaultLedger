# ADR-0002: Structured output, the repair loop, and citation verification

Date: 2026-07-27 · Status: accepted

## Context
Phase 5 makes generation reliable: the model's answer must land in the validated
`Answer` contract, malformed output must be repaired or safely downgraded (never
crash), and every surfaced fact must carry a citation that actually supports it.
SPEC 7.1 suggests the `instructor` library for structured output; SPEC 15.1/15.2
require the structured-output repair loop (L1) to be *explicit, budgeted,
observable, and deterministically terminating*, and SPEC 9.12 requires citation
verification against the retrieved set. There is a tension: `instructor` bundles
its own retry loop (tenacity-based), which is exactly the kind of hidden,
unbudgeted loop the loop-engineering rules exist to forbid.

## Options
- **`instructor` over an OpenAI-compatible endpoint, using its built-in retry.**
  Least code; idiomatic. But the retry loop is opaque — no per-iteration
  telemetry, budget lives in a library kwarg, and it adds `instructor` + `openai`
  as runtime deps plus a dependency on Ollama's `/v1` shim. Hides the one loop
  the phase is meant to demonstrate.
- **`instructor` for parsing only, with `max_retries=0` and a hand-rolled loop.**
  Keeps the named library but uses ~none of it; two ways to do one thing.
- **Ollama native JSON-schema `format` + a hand-rolled L1 repair loop
  (chosen).** Constrained decoding via the `format` field narrows malformed
  output at the source; a small `for`-bounded loop owns repair, feeds each
  validation error back into the prompt (new information per iteration), emits a
  `GuardrailEvent` per attempt, and falls back to `Answer(abstained=True)` on
  exhaustion. Zero new dependencies. The loop and the citation verifier are pure
  functions over a `StructuredGenerator` protocol, so they are testable with
  scripted generators and no live model.

## Decision
Take the native-`format` + hand-rolled-loop option. `AnswerDraft` (answer_text,
abstained, citations) is the only thing the model produces; the rich `Answer`
(tier, routing, privacy, confidence) is filled by the orchestrator, so a
hallucinated `data_left_machine` is structurally impossible. Repair budget is
`config.loops.repair_max`. This honors the SPEC 3 "no framework maximalism" rule:
build the minimal version you can explain line-by-line; `instructor` is documented
here as the drop-in alternative if/when the hosted tiers (Phase 11) make an
OpenAI-compatible client the path of least resistance.

**Citation verification is snippet-primary.** The quoted snippet is the
authoritative signal ("snippets present in the retrieved set"); the `chunk_id` is
a hint. A citation survives if its verbatim snippet is present in the claimed
chunk, or — when the model fumbles the opaque id — if the snippet is verbatim in
exactly one retrieved chunk, in which case the citation is *recovered* to that
chunk. Snippets matching zero or multiple chunks are dropped; facts with no
surviving citation downgrade to an honest abstention (tagged `CITE_FAIL`). The
anti-hallucination guarantee is unchanged: no citation survives without verbatim
supporting evidence in the retrieved set.

## Consequences
- Easier: the AC ("100 consecutive queries, zero crashes; malformed generations
  repaired or safely downgraded") is provable in CI with a scripted chaos
  generator — no Ollama in the loop. No new runtime dependency.
- Harder / watch: constrained decoding depends on the Ollama `format` field; a
  future hosted model without JSON-schema support needs the `instructor` path
  (foreseen above). Snippet recovery trusts verbatim evidence over the model's
  own id — correct here, but if a future corpus has near-duplicate chunks the
  "exactly one match" rule will (correctly) abstain more; measure it in Phase 7.
- Revisit: the numeric verifier, cross-persona check, and advice linter (the rest
  of SPEC 9.12) are Phase 13; only citation verification lands in Phase 5.

## Evidence
- `tests/test_phase5.py`: 15 deterministic tests incl. the 100-query zero-crash
  AC, repair-then-succeed, budget-bounded exhaustion, and citation
  keep/recover/drop/downgrade paths.
- Live end-to-end run over golden example `sd_009` with `qwen3:8b` +
  `nomic-embed-text` (see PROGRESS.md Phase 5) exercised the real structured
  path and the recovery guard on a genuine model id-fumble.
