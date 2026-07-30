# VaultLedger

Local-first financial-document Q&A with verified citations and a manifest-backed
evaluation harness.

VaultLedger parses synthetic bank statements, 1099s, invoices, and pay stubs on
your machine. It combines dense and lexical retrieval, reranks the evidence, and
uses a local model to answer questions. Every surfaced fact must retain a
verifiable source snippet. A privacy switch makes cloud use explicit and the
answer badge reports what actually happened, including local fallback.

**Synthetic data only.** VaultLedger is an engineering and evaluation project,
not a production financial service. It has no bank connection, contains no real
account data, and provides document extraction and Q&A, never financial advice.

## Track-A status

Phase 10 is the Track-A release candidate (`v0.1.0`). The fresh-checkout
workflow and `make verify-track-a` passed on July 30, 2026. The phase remains
open until the real browser walkthrough is recorded. Measured receipts:

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
ollama pull qwen3:8b
```

`make install` installs the Track-A package, tests, synthetic-PDF generator,
local PII tooling, and the Variant-B reranker. It also downloads spaCy's
`en_core_web_sm` model. No API key is needed for Local mode.

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
- **Experiment Lab** marks the post-Track-A expansion boundary. Multi-model
  benchmarking and policy routing begin in Phase 11; they are not claimed here.

The [Track-A demo plan](demo/README.md) contains the exact recording and
re-recording script.

## Privacy behavior

- **Local:** only local Ollama endpoints are used; routing tests socket-block the
  local path and assert that no cloud generator is called.
- **Cloud-Boosted:** disabled unless a provider URL and environment API key are
  configured and the user gives session consent.
- **Important boundary:** Track A does not yet redact PII before cloud egress.
  The corpus is synthetic, and real-document cloud use should not ship before
  Phase 13. A failed cloud request is conservatively labeled as data egress if
  its payload may already have reached the provider.

Copy `.env.example` to `.env` only for intentional synthetic-data cloud tests.
Never commit the file.

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
| `make run` | Launch Streamlit headlessly with usage telemetry disabled |

## Troubleshooting

- **`make doctor` says Ollama is unavailable:** open the Ollama app or run
  `ollama serve`, then re-run the two `ollama pull` commands.
- **The app says no ingested corpus:** run `make data && make ingest`.
- **First Ask is slow:** the BGE reranker downloads once and is cached locally.
- **Embedding-model mismatch:** delete only the derived `data/index/` directory
  and run `make ingest`; never change `config.yaml` silently around an old index.
- **Cloud selected but answered locally:** check the in-app notice. A blank URL,
  missing key, or provider failure intentionally degrades to local.

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
