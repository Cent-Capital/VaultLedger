# ADR-0018: Test an evidence-first answer policy before producing the final portfolio

2026-08-13 · Status: **accepted** · Phase 19 preregistration

## Context

Phase 18 closed two preregistered experiments as nulls. No tested model beat
`qwen3:8b`, and no tested decoding profile beat `temperature=0.0 / top_p=0.95`.
The row-level judge reasons pointed to a different lever: `FALSE_ABSTAIN` accounted for
five of the ten disagreements between the top two models and appeared again at `gs_005`
in the decoding sweep.

That label did not identify the layer causing the final abstention. Phase 19 therefore
began with a causal audit of the canonical `qwen3:8b` receipt rather than changing the
policy on the strength of a judge label. The harness-generated receipt
`receipts/phase19_abstention_baseline.json` found:

- 19 answerable rows finalized as abstentions: 15 model-declared, three output-guard
  downgrades, and one deliberate query-injection block;
- the three guard downgrades were one citation-verification downgrade and two numeric-
  verification downgrades;
- the judge labelled 15 rows `FALSE_ABSTAIN`; and
- a retrieval-only replay put an expected document in the existing top six for 14/19
  rows and in a doubled top 12 for 17/19. All 19 top rerank scores were above the typed
  `rerank_tau=0.35`.

This corrects the Phase 18 mechanism hypothesis. Citation verification is a known
faithfulness limitation because it confirms that a snippet exists rather than that it
supports the answer, but loosening it cannot explain or repair the 15 model-declared
abstentions. The SPEC's low-confidence L2 retry would trigger on none of these 19 rows.

## Options

**Loosen citation verification.** Rejected. It directly targets only one of the 19
answerable abstentions and would weaken the rule that a surfaced answer carries
verbatim evidence. A future support-aware verifier should be stricter about entailment,
not easier to bypass.

**Implement the existing low-confidence widen-retry unchanged.** Rejected as the Phase
19 experiment. The replay found zero rows below its trigger threshold. Doubling context
would add an expected document for three rows, but it would not run under the specified
trigger and cannot address the ten model-declared abstentions that already had expected
evidence in the top six.

**Retry every abstention with doubled context.** Rejected for this experiment. It adds a
second generation call to every unanswerable query, increases latency, and makes a loop
whose benefit cannot be isolated from the extra evidence. It remains a follow-up only if
the prompt experiment shows that the model can use evidence without weakening safety.

**Test one evidence-first prompt revision.** Chosen. It changes the decision instruction
before generation, where 15/19 abstentions originated, while leaving retrieval, exact-
snippet citation verification, numeric verification, injection handling, model, decoding,
context budget, and loop budgets fixed.

## Decision

Run one paired, full-80 candidate cell on `ollama/qwen3:8b`, `B_hybrid`, guardrails on,
seed 42, and the retained Phase 18 decoding profile. The frozen baseline is
`phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f`; it has the same golden-set
and configuration hashes as the Phase 19 audit.

The candidate prompt adds this decision block before the existing JSON contract:

> **EVIDENCE-FIRST DECISION:** Inspect every supplied chunk before deciding to abstain.
> A comparison, total, or summary may be supported by different chunks; no single
> snippet has to support the whole answer. When the chunks contain the requested facts,
> answer and attach one verbatim snippet for each fact. Abstain only when the supplied
> chunks do not contain enough evidence. Never infer a missing fact or relax the
> verbatim-snippet rule.

The existing instructions remain: document content is untrusted data; every surfaced
fact needs a citation; snippets must be copied verbatim; unsupported requests abstain;
and output is constrained to the same `AnswerDraft` JSON schema. The implementation
must record a prompt version or hash in the candidate manifest. No other answer-changing
code may enter the candidate commit.

### Pre-registered adoption rule

Adopt the candidate only if **all** conditions hold on the same 80 rows:

1. Answerable abstentions fall by at least four from the deterministic baseline of 19,
   and judge `FALSE_ABSTAIN` rows fall by at least four from 15.
2. Paired judge verdicts show at least four more wins than losses against the baseline.
   This is a practical threshold, not a significance claim; report exact McNemar and its
   low power separately.
3. All 10 unanswerable rows still abstain, the poisoned-document answer does not follow
   the embedded instruction, and the full Phase 13 guardrail gate remains green.
4. Citation-document hits do not fall below 57/80, strict matches do not fall below
   35/80, generation coverage remains 80/80, and `TOOL_ERR` remains zero.
5. `make test`, `make lint`, `make verify-track-a`, CI, and the synthetic corpus hash
   remain green/unchanged.

If any condition fails, retain the current prompt and report the experiment as null or
mixed. Do not tune a second prompt on these 80 rows in Phase 19.

If the candidate is adopted, the Phase 18 model and decoding matrices become historical
evidence about the old prompt. Before any final reader-facing model or decoding claim,
rerun the affected preregistered cells on the new prompt or narrow the claim explicitly.
The final portfolio must never present an old-prompt matrix as a measurement of a
new-prompt product.

## Consequences

The experiment attacks the layer that caused most observed abstentions without lowering
the evidence boundary. It also creates a real risk: a prompt that encourages answering
may convert false abstentions into unsupported or incorrect answers. That is why
unanswerable, injection, citation, judge, and strict gates are conjunctive rather than
secondary metrics.

The baseline is reused rather than rerun because it is a complete, committed 80-row
manifest at the same model, decoding, config, golden set, and guard setting. Run-to-run
model nondeterminism remains a limitation even at greedy decoding; the paired comparison
therefore supports a one-run product decision, not a general effect-size claim.

Phase 19 still owes ADR-0011's final portfolio scope: the cross-variant report, Pareto
sequence, demo v2, internship/blog artifacts, and final regression. This experiment is
the first work package, not a replacement for them.

## Evidence

- `receipts/phase19_abstention_baseline.json` — causal classification and retrieval-only
  replay, generated at Phase 19 entry.
- `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f` — frozen 80-row baseline:
  56 judge passes, 35 strict passes, 57 citation-document hits, 61 correct abstention
  decisions, zero answered-unanswerable rows.
- ADR-0016 — five of ten top-model disagreements were `FALSE_ABSTAIN`.
- ADR-0017 — decoding changed wording but moved zero strict rows; `gs_005` again exposed
  a false abstention.
