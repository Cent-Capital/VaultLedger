# VaultLedger

Local-first financial-document Q&A with verified citations and a manifest-backed
evaluation harness.

VaultLedger parses synthetic bank statements, 1099s, invoices, and pay stubs on
your machine. It combines dense and lexical retrieval, reranks the evidence, and
uses a local model to answer questions. Every surfaced fact must retain a
verifiable source snippet. Paid hosted tiers are retired by ADR-0003, so the
live product and model experiments stay on the local Ollama service.

**Synthetic data only.** VaultLedger is an engineering and evaluation project,
not a production financial service. It has no bank connection, contains no real
account data, and provides document extraction and Q&A, never financial advice.

## Track-A status

Phase 10 is the Track-A release candidate (`v0.1.0`). The fresh-checkout
workflow remains partially verified because no clean-virtualenv transcript is
committed; `make verify-track-a` passed again on August 4, 2026. Phase 10 is
closed, with the real browser walkthrough committed as the
[Track-A demo](demo/vaultledger_track_a_v1.gif). Measured receipts:

- Hybrid retrieval raised recall@20 from `0.9587` to `0.9786` and MRR from
  `0.4974` to `0.7856` on the 70 answerable examples in the 80-item golden set.
  See [the generated comparison](reports/phase4_comparison_latest.md).
- The Phase-7 local safety run rightly abstained on 10/10 unanswerable cases and
  answered the seeded poisoned-document case without following its embedded
  instruction. This is an 11-case gate, not a general 100% safety claim.
- The v1 judge separated 10 clear acceptable and 10 clear unacceptable
  calibration cases at TPR/TNR `1.00`. Those authored boundary cases do not
  establish perfect judge accuracy on ambiguous answers.
- The current retrieval regression report compares two distinct full pipeline
  runs and is green. The deliberate negative-control report is red.

The design source of truth is [SPEC.md](SPEC.md). The build receipt, including
deviations and measured boundaries, is [PROGRESS.md](PROGRESS.md).

## Tracks B/C status

The local LiteLLM gateway, matrix runner, and deterministic Phase-12 policy
router are implemented. The current [model matrix](reports/model_matrix.md)
contains full 80-case `qwen3:4b` and `qwen3:8b` Variant-B runs. The generated
[routing frontier](reports/routing_frontier.md) compares four policies over
those same cached answers, including bounded T0→T1 escalation. This is still a
two-model experiment; the two-family × three-size bake-off remains Phase 17.

The router matched its 80 initial-route labels on 100% of cases by construction.
Its useful result is the measured policy comparison: strict match was 47.5%
versus 42.5% for always-T1, at 11.0s versus 9.7s average gateway latency in one
noisy run. Both source cells covered 79/80 generations; the same case timed out
in each and is retained as a scored miss.

Phase 13 adds the named, toggleable guardrail pipeline and a generated
[guardrail acceptance report](reports/guardrail_eval.md). Its captured outbound
payload contains zero raw tagged PII and rehydrates exactly; the SQLite numeric
verifier catches the seeded wrong-total invoice; all six seeded cross-persona
leaks are blocked; and the current live injection gate remains at 100%. The
benign control result is reported honestly as 0 of 6 observed over-refusals—not
as proof that the true rate is below 5%.

## GraphRAG status

Phase 15 implements `C_graph` with LightRAG local/global retrieval, preserves
Phase-2 source chunks through the graph path for citation verification, and
exports the extracted graph as an Obsidian vault. The full local index contains
82 nodes and 206 edges over all 60 documents; its committed build receipt records
45.8 minutes, 142 completion calls, 228 embedding calls, and `$0` API spend with
local inference explicitly labelled **unpriced**, not free.

The quality result is mixed and does not justify promoting C over B. Strict entity
recall missed its preregistered gate at 11/15 (73.3%); a post-hoc, schema-derived
account alias diagnostic finds 15/15 but precision remains 15/81 (18.5%). On the
six `global_summary` rows with the shipped `qwen3:8b`, C scored 33.3% citation hit
and 33.3% abstention accuracy versus B's 66.7% and 66.7%. Those columns were
collinear on every scored row, and the two-row difference is underpowered
(`n=6`, Fisher exact two-tailed `p=0.567`). B remains the provisional default while
a pre-registered equal-context sensitivity arm checks retrieval against context
budget. That arm landed at 3/6 correct abstention behavior—exactly between B's
4/6 and C@12's 2/6—so the confound remains unresolved rather than favoring either
cause. See the generated three-arm
[Phase-15 matrix](reports/phase15_global_summary_matrix.md) and the complete
[build record](PROGRESS.md) for denominators, latency, receipts, and caveats.

The committed GraphML is enough to reproduce graph-quality scoring, but the three
gitignored LightRAG vector stores require an approximately 45-minute
`make graph-index` rebuild before a clean clone can query Variant C. Both Obsidian
export commands write `exports/obsidian_vault`; the README `Source:` line identifies
which projection was generated last, and `make graph-vault` restores the demo view.

## Fresh-machine quickstart

### 1. Prerequisites

- macOS or Linux
- Python 3.11 or newer
- [Ollama](https://ollama.com/download)
- Git
- About 10 GB free for the virtual environment and local models. The
  cross-encoder reranker downloads about 1.1 GB on the first query.

Start Ollama before ingestion. On macOS, opening the Ollama app is sufficient;
`ollama serve` is the terminal alternative.

### 2. Install

From a fresh clone:

```bash
git clone <repository-url> vaultledger
cd vaultledger
python3.11 -m venv .venv
source .venv/bin/activate
make install
ollama pull nomic-embed-text
ollama pull qwen3:4b
ollama pull qwen3:8b
```

`make install` installs the package, tests, synthetic-PDF generator, local PII
tooling, Variant-B reranker, and Phase-11 LiteLLM gateway. It also downloads
spaCy's `en_core_web_sm` model. No API key is needed.

### 3. Generate and index the synthetic corpus

```bash
make data
make ingest
make doctor
```

Expected `make doctor` result: 7/7 checks pass, including 60/60 PDFs, SQLite,
BM25, Chroma, both Ollama models, and the committed Track-A receipts. Corpus
generation is deterministic from seed `42`; `make data` may be repeated.

### 4. Verify and run

```bash
make test
make eval-smoke
make run
```

Open [http://localhost:8501](http://localhost:8501). Start in **Local** mode and
try:

> What was Marcus Chen's March closing balance?

The SPEC-by-example answer is `$4,207.55` with a citation to
`stmt_marcus_checking_2025-03`. A live local model may still abstain if it cannot
produce a verifiable citation; that safe failure is intentional.

## Full Track-A acceptance gate

```bash
make verify-track-a
```

This runs Ruff, the deterministic test suite, golden-set validation, the live
11-case safety gate, the live 20-label judge validation, and the manifest-backed
retrieval regression check. It requires Ollama with `nomic-embed-text` and
`qwen3:8b`. Local runs record `$0` API cost.

`make regression` alone is deterministic and fast. `make eval-full` is the LLM
portion of the gate. A sandbox that blocks loopback access cannot complete the
live portions; `--skip-if-unavailable` exists only for the smoke run, not for
acceptance.

## Product walkthrough

- **Library / Ingest** shows corpus health, parse failures, PII tag counts, and
  local index state. Rebuild runs the same ingestion pipeline as `make ingest`.
- **Ask** defaults to Variant B: dense + BM25, Reciprocal Rank Fusion, and local
  cross-encoder reranking. Answers show privacy outcome, verified citations,
  model/tier/variant, guard events, latency, estimated tokens, cost, and trace.
- **Evals** shows dense-to-hybrid retrieval evidence, safety and judge results,
  regression deltas, and local trace rollups.
- **Experiment Lab** surfaces the current two-model matrix and Phase-12 router
  frontier while keeping the six-model Phase-17 bake-off boundary explicit.
  Regenerate the routing report and chart with `make router-eval`.

The [Track-A demo plan](demo/README.md) contains the exact recording and
re-recording script.

## Privacy behavior

- **Local:** only local Ollama endpoints are used; routing tests socket-block the
  local path and assert that no cloud generator is called.
- **No hosted tier:** the former Cloud-Boosted UI and hosted model configuration
  were removed at Phase 11 kickoff. The generic Phase-6 routing helper remains
  covered by historical privacy/fallback regression tests, but the app cannot
  select it and the matrix cannot send a cell to it.

## Commands

| Command | Purpose |
|---|---|
| `make install` | Install Track-A development and runtime dependencies |
| `make data` | Regenerate the byte-identical synthetic PDF corpus |
| `make ingest` | Parse, extract, tag PII, chunk, and build local indexes |
| `make doctor` | Read-only setup and readiness diagnosis |
| `make lint` | Run Ruff |
| `make test` | Run deterministic phase gates |
| `make eval-smoke` | Validate the golden set and attempt a 12-case retrieval run |
| `make eval-safety` | Run the live Phase-7 safety subset |
| `make judge-validate` | Validate the local judge against 20 human labels |
| `make regression` | Compare the latest retrieval manifest with the frozen baseline |
| `make eval-full` | Run the full Track-A LLM evaluation sequence |
| `make verify-track-a` | Run lint, tests, and the full Track-A eval gate |
| `make matrix` | Run the configured local Phase-11 model matrix and regenerate its report |
| `make router-eval` | Regenerate the Phase-12 four-policy frontier from full cached matrix receipts |
| `make guardrails-eval` | Regenerate the Phase-13 named-guard acceptance report |
| `make graph-index` | Build the Phase-15 LightRAG index and versioned local-compute receipt; refuses overwrite |
| `make graph-eval` | Run the shipped-model B-vs-C comparison on all six global-summary rows |
| `make graph-eval-k6` | Run the pre-registered C_graph top-6 context sensitivity arm |
| `make graph-vault-extracted` | Rebuild the extracted graph's Obsidian projection |
| `make replay` | **Deliberately not built.** Phase 8 declined raw-input replay: storing raw questions and retrieved context would broaden local data retention against the product thesis. Exits non-zero and says so |
| `make clean` | Remove caches and build artifacts |
| `make run` | Launch Streamlit headlessly with usage telemetry disabled |

## Troubleshooting

- **`make doctor` says Ollama is unavailable:** open the Ollama app or run
  `ollama serve`, then re-run the three `ollama pull` commands.
- **The app says no ingested corpus:** run `make data && make ingest`.
- **First Ask is slow:** the BGE reranker downloads once and is cached locally.
- **Matrix model unavailable:** pull both `qwen3:4b` and `qwen3:8b`, then rerun
  `make matrix`.
- **Embedding-model mismatch:** delete only the derived `data/index/` directory
  and run `make ingest`; never change `config.yaml` silently around an old index.

## Repository map

```text
vaultledger/   typed config, ingest/index/retrieve/generate/route/evals modules
app/           Streamlit Library / Ask / Evals / Experiment Lab
data/          committed ground truth; generated PDFs and indexes are gitignored
reports/       committed RunManifests and generated comparison receipts
decisions/     Architecture Decision Records
demo/          Track-A recording and reproducible walkthrough script
tests/         phase acceptance criteria and spec-by-example gates
```

## License

Proprietary, all rights reserved. See [LICENSE](LICENSE). Created in connection
with an internship at Cent Capital LLC; not licensed for reuse.
