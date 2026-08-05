# Model matrix

Phase 11 gateway/matrix machinery proof. The full six-model bake-off is Phase 17.

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Cells: **2** across **2 model(s)**
Total measured API spend: **$0.000000** (local models are unpriced, not free)

| Model | Variant | N | Strict match | Citation hit | Abstention accuracy | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:4b` | `B_hybrid` | 80 | 40.0% | 56.2% | 57.5% | 8579 ms | 17900 ms | 154736 / 8723 | $0.000000 | `phase11_ollama_qwen3_4b_b_hybrid_61802221d874` |
| `ollama/qwen3:8b` | `B_hybrid` | 80 | 42.5% | 73.8% | 78.8% | 6602 ms | 13464 ms | 155210 / 7386 | $0.000000 | `phase11_ollama_qwen3_8b_b_hybrid_33c0a0d50c76` |

## Reading the result

`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat the reference's literal amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases and is not an LLM-judge verdict. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Gateway latency covers all completion calls, including structured-output repairs. Retrieval and reranking time is excluded. Token counts come from provider usage when available. Every displayed value is loaded from the RunManifests above; this file is generated, never hand-edited.
