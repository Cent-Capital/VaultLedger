# ADR-0015: One native Ollama chat path for product and evaluation

2026-08-12 · Status: **accepted** (required by ADR-0007 and Phase 18 kickoff)

## Context

ADR-0007 intended every product generator to match the eval gateway. Its Phase
14 fix aligned `think=false`, but a Phase 18 audit found a remaining material
split: `OllamaGenerator` sent raw `prompt` text to `/api/generate`, while the
matrix sent a user `messages` array through LiteLLM's chat-completions path.
The model's chat template therefore tokenized the same VaultLedger prompt in
the matrix but not in the product. The matrix and product were still different
systems.

Context length also diverged. LightRAG alone sent `num_ctx=32768`; reliable and
agentic generation left it to runtime/model defaults. A bake-off over either
path could not justify a product model choice.

## Decision

All active local generation uses one shared `ollama_chat_payload` builder and
Ollama's native `/api/chat` endpoint. The builder owns messages, JSON schema,
`think=false`, `temperature`, `top_p`, `top_k`, `seed`, `num_ctx`, and output-token cap.
The product wrapper, measured matrix gateway, agent planner, judge, and
LightRAG binding all receive the typed settings from `config.yaml`.

`generation.num_ctx` is explicit at `8192`, covering the bounded 12,000-character
retrieval context plus prompt/output headroom on this host and applying the same
window to reliable, agentic, and LightRAG paths. Matrix receipts
must record the complete decoding profile; model comparisons without it are not
self-describing.

The `LiteLLMGenerator` class name remains for historical imports and receipts,
but its production local branch now calls native Ollama chat and reads native
token counts. An injected LiteLLM-style completion function remains only as a
test seam. No paid or hosted path is introduced.

## Consequences

The Phase 18 bake-off now ranks the path the product uses. Native Ollama returns
`prompt_eval_count` and `eval_count`, so token accounting remains provider-based
and local cost remains `$0.0` (unpriced, not free).

This transport correction is intentionally **not** described as
behavior-neutral. `receipts/phase18_decoding_defaults.json` proves only the
earlier config promotion on the old generate endpoint. The transport is changed
because the old path was invalid for comparison, not because it reproduced the
same bytes. `receipts/phase18_product_eval_parity.json` separately compares the
new product and matrix paths on one prompt and schema, while unit tests assert
their full request payloads are identical.

Historical matrix receipts remain evidence about the old chat gateway; some
historical product/safety receipts remain evidence about the old generate path.
They are not silently relabelled as transport-parity evidence.
