# Model matrix

Manifest-backed comparison over the explicitly selected model, variants, and golden-set population. This report does not generalize beyond those cells.

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Cells: **2** across **1 model(s)**
Total measured API spend: **$0.000000** (local models are unpriced, not free)

| Model | Variant | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy | Wall p50 | Wall p95 | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:8b` | `B_hybrid` | 6 | 0.0% | — | 66.7% | 66.7% | 13046 ms | 53082 ms | 9484 ms | 24350 ms | 9301 / 906 | $0.000000 | `phase11_ollama_qwen3_8b_b_hybrid_4a099797b084` |
| `ollama/qwen3:8b` | `C_graph` | 6 | 0.0% | — | 33.3% | 33.3% | 20509 ms | 41970 ms | 12721 ms | 36476 ms | 16360 / 1380 | $0.000000 | `phase11_ollama_qwen3_8b_c_graph_f3be41d85c23` |

## By category

Category-scoped acceptance criteria must be read from this table rather than inferred from the aggregate row. `Numeric` is scored only over rows whose reference carries a numeric quantity; its `n` differs from the category `n` for that reason, and a blank cell means no row in that category is in scope.

| Model | Variant | Category | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy |
|---|---|---|---:|---:|---:|---:|---:|
| `ollama/qwen3:8b` | `B_hybrid` | `global_summary` | 6 | 0.0% | — | 66.7% | 66.7% |
| `ollama/qwen3:8b` | `C_graph` | `global_summary` | 6 | 0.0% | — | 33.3% | 33.3% |

## Reading the result

`Numeric exact match` parses every quantity out of the reference answer and requires each one to appear in the candidate as a number equal within `thresholds.numeric_epsilon`. It is the metric SPEC's numeric-exact-match acceptance criteria name, and it is deliberately *not* `strict match`: the latter compares normalized strings and scores `$1,234.50` against `1234.5` as a miss. Neither is a correctness verdict, and their biases run in opposite directions — `strict match` under-credits valid paraphrases, while numeric exact match is a presence test that cannot tell whether a figure was *used* correctly and can be satisfied by a verbose answer reciting many numbers. Read them together, and treat neither as an LLM-judge result. Rows whose reference holds no quantity, including every `unanswerable` row, are out of scope rather than scored as failures.

Every rate divides by the number of golden examples in its population, so a row that failed to produce an answer counts as a miss rather than shrinking the denominator.

`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat the reference's literal amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases and is not an LLM-judge verdict. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Wall latency covers the complete row, including retrieval, reranking, generation, repairs, and guardrails. Gateway latency covers completion calls only. Token counts come from provider usage when available and do not include retrieval-side embedding or keyword-extraction calls. Every displayed value is loaded from the RunManifests above; this file is generated, never hand-edited.
