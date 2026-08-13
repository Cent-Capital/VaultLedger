# ADR-0014: Phase 18 decoding sweep preregistration

2026-08-12 · Status: **accepted** (implements the owner-decided Phase 18 brief)

## Context

Before Phase 18, VaultLedger sent `temperature=0.0` but never sent `top_p` or
`seed`. The installed `qwen3:8b` Modelfile reports `top_p=0.95`, so `0.95` was
the effective silent value; Ollama's `0.9` engine fallback did not apply to this
model. `receipts/phase18_decoding_defaults.json` compares the old implicit
profile with explicit `temperature=0.0`, `top_p=0.95`, and `seed=42` on the same
model, prompt, schema, and pre-parity `/api/generate` transport. The two outputs
are byte-identical. That receipt proves the config promotion only; it does not
claim the later chat-transport parity correction is behavior-neutral.

The owner has already bounded the experiment to `qwen3:8b`. Sweeping all six
models would multiply a likely null experiment from six cells to 36 without
answering a different product question.

## Preregistered population and grid

- Product pipeline: `B_hybrid`, guardrails on, all 80 synthetic golden rows.
- Sweep model: `ollama/qwen3:8b` only.
- Experimental factorial grid:

  ```text
  temperature  {0.0, 0.3, 0.7}
  top_p        {1.0, 0.9}
  ```

- Baseline: the canonical six-model matrix's `qwen3:8b` cell at the promoted
  defaults, `temperature=0.0` and `top_p=0.95`. It is not rerun as a duplicate
  grid cell. The comparison therefore has seven unique decoding profiles: the
  baseline plus six experimental cells.
- Seed: `42` in every candidate and judge call. Thinking is disabled. The
  context budget and all non-decoding configuration remain fixed.
- Cost: local inference only; manifests record `$0.0` as unpriced, not free.

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
