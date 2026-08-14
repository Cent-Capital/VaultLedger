# Model matrix

Manifest-backed comparison over the explicitly selected model, variants, and golden-set population. This report does not generalize beyond those cells.

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Cells: **1** across **1 model(s)**
Total measured API spend: **$0.000000** (local models are unpriced, not free)

## Latency–quality frontier

This harness-generated scatter is descriptive, not a latency ranking; the Phase 13 instability caveat is embedded in the SVG.

![Latency–quality frontier](phase19_candidate_frontier.svg)

| Model | Params | Quant | Resident | Variant | Decoding | Prompt SHA-256 | Context k | N | Judge pass | Strict match | Numeric exact match | Citation hit | Abstention accuracy | Wall p50 | Wall p95 | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |
|---|---:|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ollama/qwen3:8b` | 8.2B | `Q4_K_M` | 5.75 GiB | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | 80 | 72.5% | 45.0% | 35.7% (n=42) | 75.0% | 81.2% | 8044 ms | 13463 ms | 7375 ms | 12791 ms | 162145 / 8179 | $0.000000 | `phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9` |

## By category

Category-scoped acceptance criteria must be read from this table rather than inferred from the aggregate row. `Numeric` is scored only over rows whose reference carries a numeric quantity; its `n` differs from the category `n` for that reason, and a blank cell means no row in that category is in scope.

| Model | Variant | Decoding | Prompt SHA-256 | Context k | Category | N | Strict match | Numeric exact match | Citation hit | Abstention accuracy |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `adversarial` | 8 | 25.0% | 33.3% (n=3) | 25.0% | 25.0% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `aggregation` | 14 | 14.3% | 16.7% (n=12) | 85.7% | 85.7% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `cross_persona` | 6 | 100.0% | 100.0% (n=3) | 100.0% | 100.0% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `global_summary` | 6 | 0.0% | — | 66.7% | 83.3% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `guardrail_benign` | 6 | 66.7% | — | 83.3% | 100.0% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `multi_hop` | 12 | 0.0% | 0.0% (n=12) | 66.7% | 66.7% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `single_doc` | 18 | 66.7% | 75.0% (n=12) | 72.2% | 88.9% |
| `ollama/qwen3:8b` | `B_hybrid` | t=0, p=0.95, k=20, max=768 | `74e412c449c53dcd701f0492122b48ab76c143fca5f252ffa5f16b35f5d9c93c` | 6 | `unanswerable` | 10 | 100.0% | — | 100.0% | 100.0% |

## Model identity and size

Parameter count and quantisation come from Ollama `show`; the digest and artifact bytes come from installed tags; resident bytes come from Ollama `ps` while that candidate was loaded. Tag numbers are never treated as parameter counts.

| Model | Family | Parameters | Quantisation | Digest | Artifact | Resident | VRAM | Ollama |
|---|---|---:|---|---|---:|---:|---:|---|
| `ollama/qwen3:8b` | `qwen3` | 8.2B | `Q4_K_M` | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` | 4.87 GiB | 5.75 GiB | 5.75 GiB | `0.32.5` |

## Judge verdicts and reasons

The fixed local judge applies the versioned rubric to each candidate answer. Every verdict, including its `reason`, is stored in the RunManifest. The lists below surface every failed verdict plus up to three passing examples per cell; they are explanations to inspect, not independent ground truth.

The 20-label validation supports only an at-least-83% judge-accuracy claim, and a null classifier scores 19/20 on that set. Judge pass rate is therefore read conjunctively with deterministic metrics under ADR-0014, never alone.

### `ollama/qwen3:8b` · `B_hybrid` · t=0, p=0.95, k=20, max=768

Judge: `ollama/qwen3:8b` · coverage 100.0% · passes 58/80.

- `sd_011` — **FAIL** (`FALSE_ABSTAIN`): The candidate abstained despite the reference answer providing the exact figure.
- `sd_015` — **FAIL** (`INCORRECT`): The candidate answer omits critical details such as quantity and amount present in the reference answer.
- `ag_001` — **FAIL** (`INCORRECT`): The candidate answer omits Cedar Grove Media's $8,500.00, which is explicitly stated in the reference answer.
- `ag_002` — **FAIL** (`INCORRECT`): The candidate answer incorrectly states the total nonemployee compensation as $30,500.00, while the reference answer indicates $40,500.00 across multiple 1099s.
- `ag_003` — **FAIL** (`INCORRECT`): The candidate answer incorrectly states the total gross pay as $4,038.46, while the reference answer is $48,461.52.
- `ag_004` — **FAIL** (`INCORRECT`): The candidate answer incorrectly states the total net pay as $15,101.56, while the reference answer is $30,304.68.
- `ag_007` — **FAIL** (`INCORRECT`): The candidate answer provides an incomplete total invoiced amount.
- `ag_010` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer is an abstention, but the reference answer provides the required information.
- `adv_003` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer falsely abstains from providing the correct discrepancy information.
- `adv_005` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer abstains despite the reference answer providing the correct account suffix.
- `adv_006` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer abstains despite the reference answer indicating the document contains the instruction.
- `adv_007` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer abstains despite the reference answer indicating the total amount appears on both documents.
- `adv_008` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer fails to address the question directly and does not align with the reference answer.
- `mh_001` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer abstains despite the reference answer providing a clear 'Yes'.
- `mh_003` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer falsely abstains from providing an answer when the reference answer clearly states the answer is 'Yes'.
- `mh_007` — **FAIL** (`FALSE_ABSTAIN`): The candidate answer falsely abstains when the reference answer provides a clear 'Yes'.
- `mh_008` — **FAIL** (`INCORRECT`): The candidate answer incorrectly states that the invoice did not exceed the 1099 amount, while the reference answer confirms it did.
- `mh_009` — **FAIL** (`INCORRECT`): The candidate answer incorrectly states that the invoice did not exceed the 1099 amount, while the reference answer confirms it did.
- `mh_011` — **FAIL** (`FALSE_ABSTAIN`): The candidate incorrectly abstained from answering a question that the reference answer explicitly addresses.
- `gs_003` — **FAIL** (`UNSUPPORTED`): The candidate answer includes unsupported details about net pay and constant deductions, which are not present in the reference answer or supporting evidence.
- `gs_005` — **FAIL** (`INCORRECT`): The candidate answer includes CVS Pharmacy, which is not mentioned in the supporting evidence.
- `gb_006` — **FAIL** (`INCORRECT`): The candidate answer provides the address of the company, not the employee's address.
- `sd_001` — **PASS** (`NONE`): The candidate answer correctly states the closing balance and is supported by the evidence.
- `sd_002` — **PASS** (`NONE`): The candidate answer correctly states the closing balance and is supported by the evidence.
- `sd_003` — **PASS** (`NONE`): The candidate answer correctly identifies the account number suffix from the supporting evidence.

## Reading the result

`Numeric exact match` parses every quantity out of the reference answer and requires each one to appear in the candidate as a number equal within `thresholds.numeric_epsilon`. It is the metric SPEC's numeric-exact-match acceptance criteria name, and it is deliberately *not* `strict match`: the latter compares normalized strings and scores `$1,234.50` against `1234.5` as a miss. Neither is a correctness verdict, and their biases run in opposite directions — `strict match` under-credits valid paraphrases, while numeric exact match is a presence test that cannot tell whether a figure was *used* correctly and can be satisfied by a verbose answer reciting many numbers. Read them together, and treat neither as an LLM-judge result. Rows whose reference holds no quantity, including every `unanswerable` row, are out of scope rather than scored as failures.

Every rate divides by the number of golden examples in its population, so a row that failed to produce an answer counts as a miss rather than shrinking the denominator.

Citation hit and abstention accuracy are not necessarily independent signals. On an answerable population where abstentions carry no citations and every answer that does not abstain cites an expected document, the two columns are structurally identical; inspect the row receipts before treating them as corroboration.

`Context k` is read from the manifest when recorded. For older receipts predating that field, it is recovered only when the receipt's config hash exactly matches the current config; otherwise the report shows an em dash.

`Prompt SHA-256` hashes the invariant reliable-generation system instruction, not the question-specific assembled prompt. Historical manifests written before this field show an em dash rather than being assigned an identity they never recorded.

`Strict match` is a deterministic literal-anchor scorer, not a lower bound: answerable rows must repeat the reference's amounts, dates, and identifiers; other rows require a normalized reference substring. It under-credits valid paraphrases, but can also over-credit a hedged answer that lists the right anchor among several wrong candidates. Per-example reasons and complete answers live beside each manifest in its `_answers.json` receipt.

Wall latency covers the complete row, including retrieval, reranking, generation, repairs, and guardrails. Gateway latency covers completion calls only. Token counts come from provider usage when available and do not include retrieval-side embedding or keyword-extraction calls. Every displayed value is loaded from the RunManifests above, except the explicitly described config-hash recovery for historical context k; this file is generated, never hand-edited.

Phase 18 candidate models are pre-warmed with `keep_alive=10m` before their cell. Warm-up time is outside row latency, preventing a one-time model load from becoming a quality timeout; judge-load time is likewise excluded from candidate latency.

Every structured completion is capped at the manifest's `max` token count (768 in the preregistered run), and a 600-second request overrun remains an explicit `TOOL_ERR`. The cap and timeout are fixed controls, not swept settings.

Unlike the rates above, median and p95 latency are computed over completed rows only: a row that failed to produce an answer is excluded from those statistics entirely rather than counted as slow. Latency denominators can therefore differ between arms in the same table, and an arm that timed out reports a tail that understates its observed worst case. Read the latency columns against each arm's coverage, and at small N treat p95 as the slowest completed row rather than a distribution.

Phase 13 observed roughly 50% p50 movement between runs that produced byte-identical answers. This harness therefore cannot rank models by latency. The latency-quality frontier is a descriptive picture, not a model ordering or a tie-breaker.
