# Model matrix

Phase 11 gateway/matrix machinery proof. The full six-model bake-off is Phase 17.

Golden set hash: `ece0ea370052e5fe97021442dd14cf5533be22d76248568e422a958d9a0e543b`  
Cells: **2** across **2 model(s)**  
Total measured API spend: **$0.000000** (local models are unpriced, not free)

| Model | Variant | N | Strict match | Citation hit | Abstention accuracy | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:4b` | `B_hybrid` | 12 | 16.7% | 33.3% | 33.3% | 3328 ms | 5854 ms | 22235 / 741 | $0.000000 | `phase11_ollama_qwen3_4b_b_hybrid_0535d0fe994f` |
| `ollama/qwen3:8b` | `B_hybrid` | 12 | 58.3% | 58.3% | 83.3% | 5380 ms | 8576 ms | 22307 / 788 | $0.000000 | `phase11_ollama_qwen3_8b_b_hybrid_59435b710ec7` |

## Reading the result

`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat the reference's literal amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases and is not an LLM-judge verdict. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Gateway latency covers all completion calls, including structured-output repairs. Retrieval and reranking time is excluded. Token counts come from provider usage when available. Every displayed value is loaded from the RunManifests above; this file is generated, never hand-edited.
