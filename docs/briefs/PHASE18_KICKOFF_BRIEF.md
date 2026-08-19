# Phase 18 kickoff — model and decoding bake-off

Opened 2026-08-12 · Implements ADR-0011 (which extends SPEC §17 / ADR-0003) · For Codex

## Entry state (verified in this session, not assumed)

`make test` and bare `pytest` both **186 passed** · `make lint` clean · **CI green** at
`71f5079` · corpus hash `ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`
· `make verify-track-a` exit 0 in 150.0s at `b69499a` · tree clean, `main` pushed.

**Phase 17 is closed on a waiver (ADR-0013).** Its code half is complete. Its machine
half — a fresh macOS Administrator-account install — is deferred in full to a single
validation pass immediately before handoff, together with checklist items A5–A7. Do
not perform it, and do not describe it as met.

## Why this phase exists

ADR-0011 recorded two gaps in the owner's own words:

> **Only one model family has ever been evaluated.** Committed receipts contain 32 runs
> on `ollama/qwen3:8b` and 5 on `ollama/qwen3:4b`. There are zero Gemma runs.

> **Decoding parameters were never a decision at all.** `temperature` is hardcoded to
> `0.0` as a Python default argument … `top_p` is never set anywhere.

Both were re-verified in this session. The receipt census reproduces exactly (32 / 5 /
0). `grep -rn "top_p" vaultledger/ app/ scripts/` still returns nothing.

Until this phase runs, **no claim may be made that `qwen3:8b` is the best available
local model** — only that it is the one the system was built and measured on
(ADR-0011). Every committed metric describes 8b.

## Scope decisions the owner has made — do not re-litigate

### Lineup: six models, two families × three sizes

| Family | Sizes | State |
|---|---|---|
| Qwen3 | `qwen3:4b`, `qwen3:8b`, `qwen3:14b` | 4b and 8b installed; **pull 14b** |
| Gemma 3 | `gemma3:1b`, `gemma3:4b`, `gemma3:12b` | 4b installed; **pull 1b and 12b** |

All four tags were confirmed to exist in the Ollama registry on 2026-08-12
(`registry.ollama.ai/v2/library/…/manifests/…` → HTTP 200 for each). Roughly 18 GB of
new weights; 233 GB free on the machine, so disk is not a constraint.

**Do not substitute `gemma:latest` or `gemma4:e2b`**, both of which are installed. They
are different *generations*, not sizes of one family, and mixing them confounds the
size axis — which is the axis this phase exists to measure.

**ADR-0003's rule stands: record each model's `ollama show` parameter count, not the
number in its tag.** Tags lie. `gemma3:4b` is not necessarily 4.0B parameters, and the
quantisation matters as much as the size. Capture parameter count, quantisation, and
the model digest in the manifest.

### Decoding: config first, then a narrow sweep

**Step 1 — promote the knobs, prove behaviour-neutral.** Add `temperature` and `top_p`
to typed config, defaulting to today's *effective* values — `temperature: 0.0`, and for
`top_p` whatever Ollama's default actually is, which must be looked up and recorded
rather than assumed. Then prove the change is behaviour-neutral: same prompt, same
model, byte-identical output before and after. ADR-0011 requires this ordering
explicitly. A sweep built on an unproven refactor measures the refactor.

While there, `seed` is recorded in every `RunManifest` and **never sent to any
generator** — verified by grep. Either plumb it through to the Ollama options or rename
the field. Recording a seed that governs nothing is exactly the class of quiet
mismatch this repo exists to avoid.

**Step 2 — sweep `qwen3:8b` only.** Pre-register the grid and the decision rule *before
running*, per the Phase-15 precedent. Suggested grid, ~6 cells:

```
temperature  {0.0, 0.3, 0.7}
top_p        {1.0, 0.9}
```

Do not sweep decoding across all six models. That is 36 cells and 8–15 hours of local
inference for what is most likely a null result, and a null result is worth reporting
but not worth that.

### Decoding parity is a hard constraint, not a nicety

ADR-0007 requires every generator the product uses to match the eval gateway's decoding
settings. A review found this is currently violated in a way that matters: `rag.py`,
`reliable.py` and `agentic.py` post a raw `prompt` to Ollama's `/api/generate`, while
`gateway/litellm_gateway.py` sends `messages=[…]` to `/chat/completions` — chat template
applied. **Same model id, different tokenisation of the same prompt.** The matrix and
the product measure different systems.

Resolve this before the bake-off, or the bake-off ranks six models on a code path the
product does not use. Also note `num_ctx` is set only in `graph/ollama_binding.py:49`
(32768) and unset everywhere else, so the reliable and agentic paths run at Ollama's
default context.

## What to build

1. **Extend the matrix runner** to sweep the lineup × variant, one `RunManifest` per
   cell. The machinery exists from Phase 11 — this is a lineup and reporting change,
   not a rewrite.
2. **Regenerate `reports/model_matrix.md`** harness-side. Never hand-edit it. Note it
   is now the canonical B_hybrid matrix; Phase 14's D_agentic cells live in
   `reports/phase14_agentic_matrix.md` and must not overwrite it again.
3. **The latency–quality frontier**, with resident model size as a secondary axis
   (ADR-0003 — the cost axis became latency when the paid tiers were retired).
   **Carry the Phase-13 caveat forward:** latency varies ~50% p50 between runs producing
   byte-identical answers, so this harness cannot currently rank models by latency. If
   that still holds, the frontier is a picture, not a ranking, and must say so.
4. **Per-model judge verdicts surfaced with their `reason` field** (SPEC §17 AC), so the
   artifact answers which model answered best *and why*.
5. **A written finding**, including a null result reported honestly if the models
   cluster. ADR-0003 names this explicitly.

## Acceptance

- [ ] Six models pulled, each with `ollama show` parameter count, quantisation and
      digest recorded in its manifest.
- [ ] `temperature` and `top_p` are typed config; the promotion is proven
      behaviour-neutral by byte-identical output at the defaults.
- [ ] `seed` either reaches the generator or is renamed.
- [ ] The product and the eval gateway use the same decoding path, or the divergence is
      recorded as a known limitation with the bake-off's scope narrowed to match.
- [ ] The decoding grid and its decision rule were committed **before** the sweep ran.
- [ ] A `RunManifest` per cell; `reports/model_matrix.md` and the frontier are
      harness-generated.
- [ ] Judge verdicts surfaced with `reason`.
- [ ] A written finding, null result included if that is the result.
- [ ] `make test`, `make lint`, `make verify-track-a`, **CI** all green; corpus hash
      unchanged.
- [ ] A `PROGRESS.md` entry with the measured numbers and the boundaries around them.

## Boundaries that must hold

- **No paid APIs, ever** (ADR-0003). Local Ollama only. Cost fields report `0.0` —
  "unpriced, not free", never "free".
- **Do not change any Phase 15 recorded result** (ADR-0010, ADR-0011). The strict
  73.3% entity recall and 13.6% precision, the alias-aware secondary's 100% recall and
  18.5% precision, the underpowered B-vs-C comparison and the inconclusive context arm
  travel forward as they are. *(Corrected 2026-08-14: this line previously paired the
  strict 73.3% recall with the alias-aware 18.5% precision — one number from each of two
  scoring schemes, which flatters the result. The recorded results themselves are
  unchanged; only this citation of them was wrong. ADR-0010 §62–63 is authoritative.)*
- **The synthetic corpus hash must stay `ba7148a112191bc8…`.** Check before and after.
- **Evals stay synthetic.** `assert_evaluation_corpus` keeps refusing user and
  OCR-derived chunks.
- **Do not perform the Phase 17 machine half** (ADR-0013).
- **Check CI with `gh run list` after pushing — do not infer it.** CI was red for seven
  consecutive pushes because nobody looked.
- **No "verified", "measured" or "tested" without a run in that session whose output you
  can show.**

## Known-open items this phase does not fix

Listed so they are not mistaken for oversights. Each needs its own pass:

- `verify_citations` confirms a quoted snippet **exists** in the retrieved set, never
  that it **supports** the answer; abstention fires only when *zero* citations survive.
- `numeric_verify` and `cross_persona_check` emit `action="pass"` when their typed-record
  population is empty.
- The agent time budget is polled at loop boundaries, not enforced on in-flight calls;
  `run_readonly_sql` has no statement timeout.
- `routing_accuracy = 100%` is a tautology — the router's only input is `category` and
  `expected_tier` is a pure function of `category`. **Relevant here:** if the bake-off
  changes which model is best per category, ADR-0004's amendment (44 of 80 rows routed
  to the empirically weaker model) gets its held-out justification. Note it; do not fit
  the map to these rows.
- `strict_answer_match` scores a hedged answer listing five candidate figures as fully
  correct, so it is not the "deterministic lower-bound scorer" the reports call it.
  **This phase depends on that metric.** At minimum, stop calling it a lower bound in
  any report this phase generates.
- The judge's 20-label validation supports "≥83% accurate", not "1.00"; a null model
  with no LLM scores 19/20 on the same set.
