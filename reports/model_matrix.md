# Model matrix

Phase 11 gateway/matrix machinery proof. The full six-model bake-off is Phase 17.

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Cells: **2** across **2 model(s)**
Total measured API spend: **$0.000000** (local models are unpriced, not free)

| Model | Variant | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:4b` | `D_agentic` | 26 | 7.7% | 8.3% (n=24) | 11.5% | 11.5% | 15386 ms | 27258 ms | 132318 / 14971 | $0.000000 | `phase11_ollama_qwen3_4b_d_agentic_7163e731454e` |
| `ollama/qwen3:8b` | `D_agentic` | 26 | 38.5% | 41.7% (n=24) | 53.8% | 57.7% | 20311 ms | 66202 ms | 90424 / 12562 | $0.000000 | `phase11_ollama_qwen3_8b_d_agentic_4c9522233d68` |

## By category

Phase 14's acceptance criterion is stated per category, so the aggregate row above cannot verify it. `Numeric` is scored only over rows whose reference carries a numeric quantity; its `n` differs from the category `n` for that reason, and a blank cell means no row in that category is in scope.

| Model | Variant | Category | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy |
|---|---|---|---:|---:|---:|---:|---:|
| `ollama/qwen3:4b` | `D_agentic` | `aggregation` | 14 | 7.1% | 8.3% (n=12) | 14.3% | 14.3% |
| `ollama/qwen3:4b` | `D_agentic` | `multi_hop` | 12 | 8.3% | 8.3% (n=12) | 8.3% | 8.3% |
| `ollama/qwen3:8b` | `D_agentic` | `aggregation` | 14 | 57.1% | 66.7% (n=12) | 71.4% | 71.4% |
| `ollama/qwen3:8b` | `D_agentic` | `multi_hop` | 12 | 16.7% | 16.7% (n=12) | 33.3% | 41.7% |

## Agent-loop controls

Compliance is computed from the complete `AgentStep` arrays stored in each answer receipt. Failed matrix rows remain misses in every rate denominator.

| Model | Trace coverage | Step budget | Token budget | Exhausted | Average / max steps | Average traced tokens |
|---|---:|---:|---:|---:|---:|---:|
| `ollama/qwen3:4b` | 100.0% | 100.0% | 100.0% | 88.5% | 5.46 / 6 | 4960 |
| `ollama/qwen3:8b` | 100.0% | 100.0% | 100.0% | 3.8% | 3.42 / 6 | 3127 |

## Reading the result

`Numeric exact match` parses every quantity out of the reference answer and requires each one to appear in the candidate as a number equal within `thresholds.numeric_epsilon`. It is the metric SPEC's numeric-exact-match acceptance criteria name, and it is deliberately *not* `strict match`: the latter compares normalized strings and scores `$1,234.50` against `1234.5` as a miss. Neither is a correctness verdict, and their biases run in opposite directions — `strict match` under-credits valid paraphrases, while numeric exact match is a presence test that cannot tell whether a figure was *used* correctly and can be satisfied by a verbose answer reciting many numbers. Read them together, and treat neither as an LLM-judge result. Rows whose reference holds no quantity, including every `unanswerable` row, are out of scope rather than scored as failures.

Every rate divides by the number of golden examples in its population, so a row that failed to produce an answer counts as a miss rather than shrinking the denominator.

`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat the reference's literal amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases and is not an LLM-judge verdict. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Gateway latency covers all completion calls, including structured-output repairs. Retrieval and reranking time is excluded. Token counts come from provider usage when available. Every displayed value is loaded from the RunManifests above; this file is generated, never hand-edited.
