# Getting started

## Prerequisites

- macOS or Linux
- **Python 3.11 or newer**
- [Ollama](https://ollama.com/download) — running before you ingest. On macOS, opening the
  Ollama app is enough; `ollama serve` is the terminal alternative.
- Git
- About **10 GB free** for the virtual environment and local models. The cross-encoder
  reranker downloads ~1.1 GB on the first query.
- *Optional, for scanned PDFs only:* `ocrmypdf` and Tesseract (`brew install ocrmypdf`).
  Text-layer PDFs never invoke either tool.

## Install

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

`make install` installs the package plus the dev, synth, reranker, and gateway extras, and
downloads spaCy's `en_core_web_sm`. **No API key is needed** — there is no hosted path.

`make install-graph` additionally installs the isolated LightRAG and NetworkX dependencies
for Variant C.

## Build the corpus and indexes

```bash
make data      # regenerate the 60-PDF synthetic corpus, byte-identical from seed 42
make ingest    # parse → extract → SQLite → PII tag → chunk → embed → Chroma + BM25
make doctor    # read-only readiness check
```

`make doctor` should report **7/7 required checks** and **1/1 optional capabilities**. It
installs, downloads, and generates nothing, and every failing check names the exact remedy
command. Start there before debugging anything else.

`make data` is deterministic and safe to repeat.

## Verify and run

```bash
make test        # 238 deterministic tests
make eval-smoke  # golden-set validation + a 12-case retrieval attempt
make run         # Streamlit on 127.0.0.1:8501, headless, telemetry off
```

Try the spec-by-example question:

> What was Marcus Chen's March closing balance?

The expected answer is `$4,207.55`, cited to `stmt_marcus_checking_2025-03`. A live local
model may still abstain if it cannot produce a verifiable citation — **that safe failure is
intentional**, not a bug.

## Using your own documents

Live user documents are deliberately kept **outside** the repository (ADR-0011). The
default inbox is `~/VaultLedger/Inbox`.

```bash
# drop text-layer PDFs into ~/VaultLedger/Inbox, then:
make live-ingest    # one stability-gated scan
make watch          # bounded polling session
```

In the app, select **User documents** independently in Library and in Ask. Startup will
**refuse** any `live.*` path that resolves inside this checkout — that refusal is the
safety mechanism, not an error to work around.

Scanned PDFs work only when `ocrmypdf` and Tesseract are installed. An OCR-derived answer
is visibly marked in the UI: **verify digits and table columns against the original.** One
clean test page is not an OCR accuracy measurement, and no accuracy claim is made.

## Every make target

### Setup and build
| Command | Purpose |
|---|---|
| `make install` | Package + dev, synth, rerank, gateway extras, and the spaCy model |
| `make install-graph` | Phase 15's isolated LightRAG + NetworkX dependencies |
| `make data` | Regenerate the byte-identical synthetic corpus |
| `make ingest` | Parse, extract, tag PII, chunk, and build local indexes |
| `make doctor` | Read-only setup and readiness diagnosis |
| `make run` | Launch Streamlit without telemetry or first-run prompts |
| `make clean` | Remove caches and build artifacts |

### Live documents
| Command | Purpose |
|---|---|
| `make live-ingest` | Scan the external inbox once, after the file-stability gate |
| `make watch` | Watch the external inbox for the configured finite poll budget |

### Gates
| Command | Purpose |
|---|---|
| `make lint` | Ruff |
| `make test` | Deterministic phase gates, incl. the `while True` ban |
| `make eval-smoke` | Golden-set validation + a 12-case retrieval attempt |
| `make eval-safety` | Live Phase-7 subset: 10 unanswerable + the poisoned document |
| `make judge-validate` | Judge against 20 human labels; exits non-zero below 0.80 |
| `make regression` | Latest retrieval manifest vs the frozen baseline |
| `make eval-full` | The full LLM evaluation sequence |
| `make verify-track-a` | `lint` + `test` + `eval-full` — the phase gate as one target |

### Experiments (long-running, local inference)
| Command | Purpose | Rough cost |
|---|---|---|
| `make matrix` | Six-model `B_hybrid` bake-off | ~2.5 h |
| `make decoding-sweep` | Preregistered temperature × top-p grid | ~2.3 h |
| `make router-eval` | Four-policy frontier over cached receipts | fast |
| `make guardrails-eval` | Named-guard acceptance report | ~4 s |
| `make agentic-eval` | Variant D on its 26 target rows, guards on | minutes |
| `make agentic-safety` | Phase-7 suite with Variant D live | ~2 min |
| `make graph-index` | Full LightRAG build; refuses to overwrite | **~45.8 min** |
| `make graph-eval` | Same-model B-vs-C on all 6 global-summary rows | minutes |

### Analysis (read receipts, run nothing)
| Command | Purpose |
|---|---|
| `make variant-matrix` | A/B/C/D comparison from committed receipts |
| `make failure-pareto` | Failure-taxonomy sequence, snapshots discovered by rule |
| `make adr-index` | Decision index with outcome classes |
| `make abstention-audit` | Classify abstention causes; replay retrieval, no generation |

### Deliberately not built
| Command | Why |
|---|---|
| `make replay` | Phase 8 declined raw-input replay: persisting raw financial questions and retrieved context would broaden local data retention against the product thesis. Exits non-zero and says so. |

## Troubleshooting

- **`make doctor` says Ollama is unavailable** — open the Ollama app or run `ollama serve`,
  then re-run the three `ollama pull` commands.
- **"No ingested corpus"** — run `make data && make ingest`.
- **First Ask is slow** — the BGE reranker downloads ~1.1 GB once and is cached.
- **Embedding-model mismatch** — delete only the derived `data/index/` directory and re-run
  `make ingest`. Never change `config.yaml` silently around an existing index; the Chroma
  collection records its embedding model and will refuse queries from a different one.
- **A scan fails with missing OCR tools** — install both `ocrmypdf` and Tesseract, then
  re-drop the file so the watcher retries it.
- **Live path rejected at startup** — keep the inbox and every derivative outside the
  checkout, e.g. under `~/VaultLedger/`. A gitignored directory inside the repo is not safe
  enough and is refused by design.
- **macOS says the launcher is from an unidentified developer** — right-click
  `Launch VaultLedger.command`, choose **Open**, then **Open** again. One-time; the app is
  not code-signed (ADR-0011).
