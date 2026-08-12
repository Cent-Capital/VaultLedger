# Model matrix

Manifest-backed comparison over the explicitly selected model, variants, and golden-set population. This report does not generalize beyond those cells.

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Cells: **2** across **2 model(s)**
Total measured API spend: **$0.000000** (local models are unpriced, not free)

| Model | Variant | Context k | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy | Wall p50 | Wall p95 | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:4b` | `D_agentic` | — | 26 | 7.7% | 8.3% (n=24) | 11.5% | 11.5% | — | — | 15386 ms | 27258 ms | 132318 / 14971 | $0.000000 | `phase11_ollama_qwen3_4b_d_agentic_7163e731454e` |
| `ollama/qwen3:8b` | `D_agentic` | — | 26 | 38.5% | 41.7% (n=24) | 53.8% | 57.7% | — | — | 20311 ms | 66202 ms | 90424 / 12562 | $0.000000 | `phase11_ollama_qwen3_8b_d_agentic_4c9522233d68` |

## By category

Category-scoped acceptance criteria must be read from this table rather than inferred from the aggregate row. `Numeric` is scored only over rows whose reference carries a numeric quantity; its `n` differs from the category `n` for that reason, and a blank cell means no row in that category is in scope.

| Model | Variant | Context k | Category | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy |
|---|---|---:|---|---:|---:|---:|---:|---:|
| `ollama/qwen3:4b` | `D_agentic` | — | `aggregation` | 14 | 7.1% | 8.3% (n=12) | 14.3% | 14.3% |
| `ollama/qwen3:4b` | `D_agentic` | — | `multi_hop` | 12 | 8.3% | 8.3% (n=12) | 8.3% | 8.3% |
| `ollama/qwen3:8b` | `D_agentic` | — | `aggregation` | 14 | 57.1% | 66.7% (n=12) | 71.4% | 71.4% |
| `ollama/qwen3:8b` | `D_agentic` | — | `multi_hop` | 12 | 16.7% | 16.7% (n=12) | 33.3% | 41.7% |

## Agent-loop controls

**Trace coverage, step budget and token budget are invariants, not results.** The loop appends exactly one step per iteration over a fixed range and charges tokens through `min(..., budget - used)`, so all three read 100% by construction — a planner that never returns a valid action still scores 100% on every one. They are regression guards: if one ever drops, the loop's bookkeeping is broken. They are **not** evidence that the agent behaved well, and must never be reported as a measured safety property.

`Exhausted` is the only column here that varies with model behaviour, and it is the one worth reading. Note that a wall-clock exhaustion caused by an unreachable generator is a transport failure, not a model failure; the two are labelled separately in the step trace (ADR-0007).

Computed from the complete `AgentStep` arrays in each answer receipt. Rates divide by all golden examples in the cell, so a failed row stays a miss; the step and token averages divide only by rows that ran.

| Model | Trace coverage | Step budget | Token budget | Exhausted | Average / max steps | Average traced tokens |
|---|---:|---:|---:|---:|---:|---:|
| `ollama/qwen3:4b` | 100.0% | 100.0% | 100.0% | 88.5% | 5.46 / 6 | 4960 |
| `ollama/qwen3:8b` | 100.0% | 100.0% | 100.0% | 3.8% | 3.42 / 6 | 3127 |

## Reading the result

`Numeric exact match` parses every quantity out of the reference answer and requires each one to appear in the candidate as a number equal within `thresholds.numeric_epsilon`. It is the metric SPEC's numeric-exact-match acceptance criteria name, and it is deliberately *not* `strict match`: the latter compares normalized strings and scores `$1,234.50` against `1234.5` as a miss. Neither is a correctness verdict, and their biases run in opposite directions — `strict match` under-credits valid paraphrases, while numeric exact match is a presence test that cannot tell whether a figure was *used* correctly and can be satisfied by a verbose answer reciting many numbers. Read them together, and treat neither as an LLM-judge result. Rows whose reference holds no quantity, including every `unanswerable` row, are out of scope rather than scored as failures.

Every rate divides by the number of golden examples in its population, so a row that failed to produce an answer counts as a miss rather than shrinking the denominator.

Citation hit and abstention accuracy are not necessarily independent signals. On an answerable population where abstentions carry no citations and every answer that does not abstain cites an expected document, the two columns are structurally identical; inspect the row receipts before treating them as corroboration.

`Context k` is read from the manifest when recorded. For older receipts predating that field, it is recovered only when the receipt's config hash exactly matches the current config; otherwise the report shows an em dash.

`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat the reference's literal amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases and is not an LLM-judge verdict. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Wall latency covers the complete row, including retrieval, reranking, generation, repairs, and guardrails. Gateway latency covers completion calls only. Token counts come from provider usage when available and do not include retrieval-side embedding or keyword-extraction calls. Every displayed value is loaded from the RunManifests above, except the explicitly described config-hash recovery for historical context k; this file is generated, never hand-edited.

Unlike the rates above, median and p95 latency are computed over completed rows only: a row that failed to produce an answer is excluded from those statistics entirely rather than counted as slow. Latency denominators can therefore differ between arms in the same table, and an arm that timed out reports a tail that understates its observed worst case. Read the latency columns against each arm's coverage, and at small N treat p95 as the slowest completed row rather than a distribution.
