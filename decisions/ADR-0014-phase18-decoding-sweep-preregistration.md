# ADR-0014: Phase 18 decoding sweep preregistration

2026-08-12 · Status: **accepted; amended 2026-08-13 before the first sweep cell**

## Context

Before Phase 18, VaultLedger sent `temperature=0.0` but never sent `top_p` or
`seed`. The installed `qwen3:8b` Modelfile reports `top_p=0.95`, so `0.95` was
the effective silent value; Ollama's `0.9` engine fallback did not apply to this
model. The product decodes greedily at `temperature=0.0`, so promoting `top_p`
to explicit config cannot change which token is selected, and
`receipts/phase18_decoding_defaults.json` confirms the output stayed identical.
That byte comparison is not discriminating evidence on its own: the probe also
uses a `const` schema that admits only one answer. The value `0.95` is justified
separately by the proof script's enforced cross-check against the installed
model's own `/api/show` parameters. The receipt covers config promotion only;
it does not claim the later chat-transport correction is behavior-neutral.

The owner has already bounded the experiment to `qwen3:8b`. Sweeping all six
models would multiply a likely null experiment from six cells to 36 without
answering a different product question.

## Preregistered population and grid

- Product pipeline: `B_hybrid`, guardrails on, all 80 synthetic golden rows.
- Sweep model: `ollama/qwen3:8b` only.
- Experimental factorial grid:

  ```text
  temperature  {0.3, 0.7}
  top_p        {1.0, 0.9, 0.8}
  ```

- Baseline: the canonical six-model matrix's `qwen3:8b` cell at the promoted
  defaults, `temperature=0.0` and `top_p=0.95`. It is not rerun as a duplicate
  grid cell. The comparison therefore has seven unique decoding profiles: the
  baseline plus six experimental cells where nucleus sampling is live.
- Seed: `42` in every candidate and judge call. Thinking is disabled. The
  actual context window is `8192`, structured output is capped at `768` tokens,
  `top_k=20` is explicit, and request timeout is `600` seconds in every product
  and eval call. Those are fixed controls, not sweep dimensions. `top_k=20`
  preserves the installed qwen3:8b default while preventing a live sampling
  parameter from disappearing from the manifest. The retrieval context budget
  and all other non-decoding configuration remain fixed.
- Cost: local inference only; manifests record `$0.0` as unpriced, not free.

The context value was selected before the experimental sweep after a mechanics-only
smoke exposed that `qwen3:14b` could not complete even one row within 600 seconds
at `32768`. VaultLedger assembles at most 12,000 context characters, so `8192`
retains headroom for the prompt and output while avoiding a host-infeasible KV
allocation. Every model receives the same value; the large model gets no exception.

The 2026-08-13 amendment replaces the originally registered temperature-zero
cells `(0.0, 1.0)` and `(0.0, 0.9)` with `(0.3, 0.8)` and `(0.7, 0.8)`.
At greedy temperature, `top_p` is inert, so both old cells duplicated each other
and the `0.0 / 0.95` baseline and could never satisfy the decision rule. The
replacement spends the same six-cell budget where the swept parameter is live.
This correction was committed before any full-population sweep cell ran; the
earlier N=1 default-profile smoke is mechanics evidence, not a sweep result.

The grid in `config.yaml` and this decision record must be committed before any
sweep cell runs. A smoke test of runner mechanics is not an experimental cell
and cannot be included in the finding.

## Preregistered decision rule

The current defaults remain the product setting unless an experimental cell
meets **all** of these paired, full-population conditions against the baseline:

1. At least four additional rows pass both the existing strict scorer and the
   LLM judge (a five-percentage-point improvement over 80 rows).
2. Numeric exact-match count, citation-hit count, abstention-correct count, and
   completed-generation count do not decrease.
3. Review of every newly passing judge verdict's `reason` finds a concrete
   correctness or faithfulness improvement. A reason that merely notes shared
   wording, or a hedged answer that lists the right anchor among wrong
   candidates, does not qualify.
4. No guardrail acceptance metric regresses.

If more than one cell qualifies, choose the one with the most judge passes,
then most numeric exact matches, then most strict matches. A remaining tie goes
to lower temperature and then the `top_p` closest to the current `0.95`.

If no cell qualifies, retain `0.0 / 0.95` and report the sweep as a null or
inconclusive result. There is no latency tie-break: Phase 13 observed roughly
50% p50 movement between runs with byte-identical answers, so this harness
cannot rank decoding profiles by latency.

## Measurement boundaries

`strict_answer_match` is not called a lower bound in Phase 18 output. It can
credit a hedged answer that contains the expected anchors among extra candidate
figures. The judge is also weak evidence: its 20-label validation supports only
an at-least-83% accuracy claim, and the same set gives a null classifier 19/20.
The conjunctive rule and reason review reduce those risks; they do not turn
either metric into ground truth.

The experiment is descriptive and paired over this synthetic corpus. It does
not establish a universal decoding optimum, and it does not generalize to the
other five models, user documents, OCR-derived chunks, or hosted models.
