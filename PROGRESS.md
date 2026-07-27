# PROGRESS

Honest build log. One entry per phase: what got built, what deviated from
SPEC.md and why, and a plain-English explainer of the trickiest piece (that
paragraph is the interview prep). No backdating, no compressing — the commit
history is the receipt.

---

## Phase 0 — Scaffold & config  (2026-07-11)

**Built**
- Repository structure per SPEC Section 17 (package + subpackages, `app/`,
  `data/`, `reports/`, `decisions/`, `tests/`, CI).
- `vaultledger/schemas.py` — all Section 8.1 data contracts as Pydantic v2
  models (DocMeta, Chunk, Citation, RoutingDecision, GuardrailEvent, AgentStep,
  Answer, QAExample, RunManifest).
- `vaultledger/config.py` + `config.yaml` — typed loader over the Appendix B
  config (seed, budgets, loop caps, thresholds, model/tier registry).
- `app/streamlit_app.py` — the four screens (Library / Ask / Evals /
  Experiment Lab) as booting placeholders; sidebar renders live config.
- `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`, README.
- CI (`.github/workflows/ci.yml`): ruff + schema-import check + `while True`
  lint (SPEC 15.2) + pytest.
- `tests/test_phase0.py` — Phase 0 acceptance criteria as tests.
- ADR-0001 (baseline stack).

**Acceptance criteria** — met.
- App boots: `streamlit run` serves and `/_stcore/health` returns `ok`.
- Schemas import: `import vaultledger.schemas` clean; nested `Answer` validates.
- Config loads: `load_config()` returns typed values (seed=42, budget=$40, etc.).

**Deviations from SPEC**
- Schema definition order: SPEC 8.1 lists `Answer` before the models it
  references. Defined the leaf models (RoutingDecision, GuardrailEvent,
  AgentStep) first so imports need no `model_rebuild()`. Field names and types
  are unchanged from the spec.
- Added `model_config = ConfigDict(protected_namespaces=())` on `Answer` so the
  `model_used` field doesn't trip Pydantic's protected `model_` namespace
  warning. No behavior change.

**Trickiest piece (plain English)**
`config.py` uses `pydantic-settings` with a custom source order so `config.yaml`
is the canonical source of truth, but an environment variable can still override
a single value for CI or a one-off run. The loader validates the YAML into typed
objects at startup, so a malformed config fails immediately with a clear error
instead of blowing up deep inside a retrieval loop later. That "fail loud at the
boundary" habit is why every knob in the system routes through one typed object.

**Model performance notes (measured 2026-07-13, Phase 2)**
- Dev machine RAM: 16 GB (confirms the ≤24 GB model lineup; `qwen3:30b-a3b` is out)
- `qwen3:8b` generation: 20.4 tok/s (prompt eval 96.8 tok/s) — one-shot `ollama run --verbose`
- `qwen3:4b` generation: 38.5 tok/s (prompt eval 146.9 tok/s) — same method

**Next:** Phase 1 — synthetic data (entity-rich corpus + ground truth +
poisoned doc + wrong-total doc), regenerable byte-identical from the seed.

---

## Phase 1 — Synthetic data  (2026-07-13)

**Built**
- `vaultledger/synth/` — deterministic corpus generator:
  - `personas.py` — the fixed cast (3 personas, 3 orgs, merchant lists) and the
    intended relationships.
  - `records.py` — typed records for all 60 docs (SPEC 8.2 shapes) + the
    `entities.json` relation graph, from one seeded RNG in a fixed order.
  - `render.py` — `fpdf2` renderer, two visual layouts per doc type,
    byte-deterministic.
  - `build.py` + `__main__.py` — orchestrator; `python -m vaultledger.synth`
    (also `make data`) writes PDFs + per-doc ground-truth JSON + entities.json.
- **60 documents:** 24 bank statements (4 accounts x 6 months), 12 pay stubs,
  5 1099s, 19 invoices (incl. the near-duplicate).
- **Entity richness (SPEC 8.3), all present and test-verified:** Nimbus is both
  Marcus's pay-stub employer and David's 1099 payer; Halcyon/Cedar Grove appear
  on invoices *and* as 1099 payers; Marcus holds two accounts (aggregation);
  the five recurring merchants hit every monthly statement; the Nimbus address
  is shared across Marcus's pay stubs and David's 1099.
- **Deliberate hard cases:** injection line embedded in Marcus's March checking
  statement; one invoice whose printed total (`$16,431.22`) disagrees with its
  line-item sum (`$16,251.22`); one near-duplicate invoice; abstention targets
  (credit score, SSN, loan balance) intentionally absent from the corpus.
- **Spec-by-example anchors baked in:** E1 (Marcus March closing `$4,207.55`),
  E2 (Priya's two 1099s, `$12,000 + $8,500 = $20,500`).
- `tests/test_phase1.py` — 16 ACs, each re-derived from the generated corpus
  (the `entities.json` booleans are never trusted alone).

**Acceptance criteria** — met.
- Regenerate byte-identical from the seed: two fresh builds hash-match across all
  121 files; committed ground-truth JSON equals a fresh build byte-for-byte.
- Entity requirements verifiably present: independent tests confirm each 8.3
  relationship from the records.
- Adversarial line present: pdfplumber confirms the exact injection string is on
  the poisoned statement's page and absent from a clean statement.

**Deviations from SPEC**
- **Faker dropped; fixed cast + seeded `random` instead.** The cross-document
  relationships are *requirements*, not samples — they must be guaranteed, and
  Faker output can drift across versions, which would threaten the byte-identity
  AC. Names/addresses are hand-fixed (and obviously synthetic); only amounts,
  dates, and occasional-merchant sprinkle are randomized from the seed. Faker is
  not a dependency (don't declare deps we don't use).
- **fpdf2 over reportlab** (both listed as acceptable in 7.1): fpdf2's pinnable
  creation date makes byte-identity straightforward. No ADR — within the stated
  default.
- **pdfplumber pulled forward** (a Phase 2 dep) into the dev/test extra so the
  Phase-1 tests can read the rendered PDFs back and *prove* the injection and the
  wrong printed total are on the page. Runtime deps unchanged.
- **Invoice `bill_to` lives in the ground-truth `entities` block, not `record`.**
  SPEC 8.2's invoice schema names `vendor` (the issuer) but no client field; the
  typed `record` stays exactly the 8.2 shape while the client<->1099 edge stays
  explicit and scoreable. Similarly `account_type` is added to statement records
  (a harmless superset) to disambiguate Marcus's two accounts.

**Trickiest piece (plain English)**
Byte-identical PDF regeneration. A PDF normally embeds the wall-clock time it was
created and a library/version string, so two runs — or a laptop and CI — produce
different bytes even from identical content. Three pins fix that: a
timezone-anchored constant creation date (a naive datetime would pick up the
host timezone and diverge), fixed producer/author strings, and core fonts only
(no embedded-font nondeterminism). Why it matters: the corpus is the *fixture*
every later eval trusts. If the data silently shifted between runs, every
downstream metric would be measuring against a moving target and "did retrieval
improve?" becomes unanswerable. Related pin: to land E1's exact `$4,207.55`
closing while keeping the statement self-consistent (closing = opening + sum of
transactions), the generator appends one honest balancing line ("Monthly
Interest") rather than fudging the printed number — the document still reconciles.

**Next:** Phase 2 — ingestion & indexing (parse -> type/extract -> SQLite ->
PII-tag -> chunk -> embed -> Chroma + BM25).

---

## Phase 2 — Ingestion & indexing  (2026-07-13)

**Timeline note (owner decision, 2026-07-13):** whole project compressed to
finish by **Aug 10** (Track A by ~Jul 26). SPEC Section 0/16 dates updated in
this commit. Nothing is backdated; the pace changed, not the honesty rules.

**Built**
- `vaultledger/ingest/` — the pipeline (SPEC 9 steps 1–5):
  - `parse.py` — pdfplumber text + word geometry; per-page global char offsets.
  - `classify.py` — keyword-heuristic doc typing (LLM classifier not needed:
    heuristic scores 60/60 against ground truth, and it's free + deterministic).
  - `records.py` — SPEC 8.2 typed records as Pydantic models (extraction side).
  - `extract.py` — layout-aware extractors for all 4 types x 2 layouts.
  - `pii.py` — Presidio analyzer (spaCy `en_core_web_sm`) + a custom recognizer
    for masked account numbers (`****4021`), which stock recognizers can't see.
  - `chunk.py` — line-packing chunker (~600 tokens, 15% overlap), page-bounded;
    every chunk is a literal `full_text[start:end]` slice.
  - `store.py` — SQLite: one table per record type + child tables (transactions,
    line items, 1099 boxes, deductions), REAL amounts, queryable by the later
    `sql` tool and numeric verifier.
  - `pipeline.py` / `__main__.py` — orchestrator; `python -m vaultledger.ingest`
    (also `make ingest`); one bad doc is recorded as failed, never aborts.
- `vaultledger/index/` — `embed.py` (Ollama `nomic-embed-text`), `vector.py`
  (persistent Chroma; collection records its embedding model and refuses
  queries from a different one), `bm25.py` (rank_bm25 + persisted token corpus).
- Streamlit Library screen now real: document table (type, period, pages, PII
  tag count, status), corpus metrics, "Rebuild indexes" button.
- Config: `embedding` / `chunking` / `paths` sections in config.yaml + typed
  loaders. `data/index/` gitignored (derived, rebuildable).
- `tests/test_phase2.py` — 15 ACs.

**Acceptance criteria** — met (fresh run: 60/60 docs, 0 failures, 60 chunks).
- All docs ingested: pipeline builds corpus from scratch in tests; 60 ok.
- Chunks carry exact spans: every chunk equals `full_text[char_start:char_end]`
  and sits inside its page's char range — asserted for the whole corpus.
- Typed records validate: every extracted record is compared **field-by-field
  against ground-truth JSON the extractor never reads** — balances,
  transactions (incl. debit/credit direction), 1099 box amounts, invoice line
  items, deductions all match across all 60 docs.
- PII tags stored: every doc tagged; US_BANK_NUMBER on all statements (via the
  custom masked-account recognizer); PERSON on >= 90% of docs.
- Similarity query sane: live Ollama vector query returns the right doc types
  in top-3 for statement- and pay-stub-shaped questions; BM25 topical queries
  land on the right doc types.

**Deviations from SPEC**
- **Keyword heuristic over LLM classifier** (SPEC 9.2 allows either): 60/60
  accuracy, deterministic, free. Revisit only if a non-synthetic corpus breaks it.
- **spaCy `en_core_web_sm` instead of Presidio's default `en_core_web_lg`**:
  ~40x smaller, adequate recall here; model name pinned in `pii.py`.
- **Line-packing chunker instead of recursive character splitting** (SPEC 8.4's
  intent, different mechanism): financial docs are line-structured; packing
  whole lines guarantees no transaction row is ever split, which recursive
  char-splitting can only approximate. Budget ~600 tokens is inside 8.4's range.
- **Extraction stores the printed invoice total, not the recomputed one** — by
  design: the seeded wrong-total invoice must survive extraction wrong, so the
  Phase 13 numeric verifier has something real to catch (test-asserted).
- Layout-B invoices print no issue date → `issue_date` NULL for those records;
  extraction reports only what the page supports.

**Honest findings for later phases**
- The corpus yields exactly 1 chunk per doc at ~600-token budget (these docs
  are small). Retrieval evals in Phase 3/4 are therefore doc-granularity; if
  that makes recall@k trivially easy, shrink `chunking.max_chars` and re-run —
  it's one config knob and the manifest records it.
- **BM25 cannot disambiguate shared entities**: "1099 from Halcyon" ranks other
  layout-A 1099s (which repeat "Nonemployee Compensation" twice) above the
  Halcyon 1099, because "Halcyon" also appears in ~20 invoices (weak IDF).
  First concrete RANK_MISS-shaped motivation for Phase 4 hybrid + rerank.

**Trickiest piece (plain English)**
Statement layout A prints debits and credits in separate columns, and flat PDF
text extraction destroys exactly that distinction — both come out as "date,
description, amount" with no hint of which column the amount sat in. Get it
wrong and every downstream aggregation ("how much did I spend in March?")
silently flips sign, poisoning ground-truth scoring and the numeric verifier.
The fix reads word *geometry* instead of text: pdfplumber reports each word's
horizontal position, the renderer's column layout puts the debit column's right
edge at ~470pt and the credit column's at ~567pt, so an amount ending left of
the midpoint is a debit, right of it a credit. The Phase 2 tests then verify
every transaction's direction against ground truth across all 24 statements —
the geometry trick isn't trusted, it's measured.

**Next:** Phase 3 — naive RAG (variant A) end-to-end + the ~80-item golden set
+ baseline metrics in a RunManifest.

---

## Phase 3 — Naive RAG + golden set  (2026-07-13)

**Built**
- `vaultledger/retrieve/` — Variant A dense baseline:
  - `types.py` — shared `Retriever` protocol + `ScoredChunk`.
  - `naive.py` — Chroma dense top-k over Phase-2 chunks using the pinned
    Ollama embedding model.
  - `context.py` — simple rank-order context assembly with explicit
    "UNTRUSTED DOCUMENT CONTENT" wrapping.
- `vaultledger/generate/` — minimal local generation path:
  - `ollama.py` — local Ollama wrapper; strips `ollama/` model ids from config.
  - `rag.py` — retrieve -> assemble -> generate -> `Answer` contract with local
    T1 routing metadata and citation snippets.
- `vaultledger/evals/` — Phase-3 harness:
  - `golden_set.yaml` — 80 examples, versioned as `golden_set_v2_phase3`, with
    category mix matching SPEC 8.5 (18 single_doc, 14 aggregation, 10
    unanswerable, 8 adversarial, 12 multi_hop, 6 global_summary, 6
    guardrail_benign, 6 cross_persona).
  - `golden.py` — loader, hash, and snippet-anchor validation.
  - `metrics.py` — retrieval recall@k, precision@k, MRR, hit-rate, and
    `RANK_MISS` failure records.
  - `run.py` / `__main__.py` — `python -m vaultledger.evals validate` and
    `python -m vaultledger.evals run`.
- Streamlit Ask screen now runs the local Variant-A path when Ollama is
  reachable; Evals screen points to the CLI harness.
- `Makefile` now uses the repo `.venv` automatically when present and wires
  `make eval-smoke` to golden-set validation + a 12-example baseline attempt.
- README status updated from stale Phase 0 text to the current Phase 3 state.
- `tests/test_phase3.py` — deterministic tests for golden-set shape/snippets,
  retrieval metrics, untrusted context wrapping, and answer contract assembly.

**Acceptance criteria** — met with caveats below.
- Grounded cited answer on a golden question:
  `reports/phase3_b4407e88d3ba_answer.json`, example `sd_009`, answers
  "Halcyon Retail Group" and cites `inv_david_halcyon_01#c0`;
  `citation_docs_match_expected=true`.
- Full set runs: real local run over all 80 golden examples wrote
  `reports/phase3_b4407e88d3ba.json` and `reports/phase3_baseline_latest.json`.
- Baseline metrics recorded in a RunManifest:
  - `run_id`: `phase3_b4407e88d3ba`
  - `git_sha`: `85ea6f7b6943bd930ab2d68d3e5dfb6b898e00ca`
  - `golden_set_hash`:
    `ece0ea370052e5fe97021442dd14cf5533be22d76248568e422a958d9a0e543b`
  - `retrieval_recall@20`: `0.9586734693877551`
  - `retrieval_precision@20`: `0.1007142857142856`
  - `retrieval_mrr`: `0.49739239518651296`
  - `retrieval_hit_rate`: `0.9857142857142858`
  - `retrieval_eval_coverage`: `0.875` (70 answerable examples / 80 total;
    unanswerable questions are excluded from retriever-only metrics)
  - `total_cost_usd`: `0.0`

**Verification**
- `make lint` — passed (`ruff check .`, all checks passed).
- `make test` — passed (`41 passed, 1 skipped`).
- `python -m vaultledger.evals validate` — passed (`80 examples`,
  hash prefix `ece0ea370052`).
- `make eval-smoke` — golden validation passed, then the dense mini-run skipped
  under sandboxed localhost access with the honest message that Ollama was
  unavailable. The full baseline run was executed separately with approved
  local-Ollama access and produced the manifest above.

**Deviations from SPEC**
- Phase 3 records **retrieval metrics only** in the baseline manifest. Full
  generation correctness, faithfulness, abstention confusion matrix, and
  citation-verification scoring are Phase 5/7/9 work per SPEC; this phase proves
  the end-to-end path with one generated cited answer and keeps the measured
  full-set metrics to the retriever, where scoring is deterministic today.
- `make eval-smoke` is designed to skip the dense mini-run if Ollama is not
  reachable, while still validating the golden set. This keeps ordinary CI/local
  shells from failing on missing local model runtime; acceptance runs must use
  the real `python -m vaultledger.evals run` path and produce a RunManifest.
- The simple Phase-3 answer path attaches the top retrieved snippets as
  citations; it does not yet parse/verify the model's claimed citations. That is
  intentionally left for the structured-output and citation-verification phases.

**Honest findings for Phase 4**
- Dense-only retrieval misses relationship/global-summary cases even at k=20.
  The six `RANK_MISS` failures in the baseline manifest are:
  `mh_008`, `mh_012`, `gs_001`, `gs_003`, `gs_004`, `gs_006`.
- The first generated-answer probe (`sd_001`) produced the right answer text but
  attached nearby Marcus statement citations rather than the March statement.
  That artifact is retained as `reports/phase3_6fc894fd69cf_answer.json` as a
  useful failure example. The accepted grounded-answer artifact is
  `reports/phase3_b4407e88d3ba_answer.json`.

**Trickiest piece (plain English)**
The important distinction in Phase 3 is "retrieval can be measured
deterministically; generation cannot be trusted just because it sounds right."
The naive dense retriever often finds the right neighborhood but not the exact
document first — for example, Marcus's March closing balance also appears as
April's beginning balance, so a model can answer correctly while the citation is
not the source the question asked for. That is why the manifest scores retrieval
against expected doc IDs before generation, and why the generated-answer artifact
now includes an explicit `citation_docs_match_expected` flag. The failure is not
hidden; it becomes the Phase-4 reason to add lexical search, RRF, reranking, and
later citation verification.

**Next:** Phase 4 — hybrid retrieval (dense + BM25 + RRF + rerank), before/after
table versus `phase3_b4407e88d3ba`, and measured MRR/recall improvement.

---

## Phase 4 — Retrieval quality  (2026-07-13)

**Built**
- `vaultledger/retrieve/hybrid.py` — Variant B behind the existing `Retriever`
  interface: dense and BM25 candidates, deterministic Reciprocal Rank Fusion
  (`k=60`), then an optional second-stage ranker.
- `vaultledger/retrieve/rerank.py` — lazy local cross-encoder wrapper for
  `BAAI/bge-reranker-base`; raw logits are bounded for the `Answer.confidence`
  contract without claiming the resulting score is calibrated.
- Typed retrieval/reranker knobs in `config.yaml`: candidate pool, RRF constant,
  generation top-n, model, and batch size. `sentence-transformers` is isolated in
  the `rerank` dependency extra; `make install` includes it because Variant B is
  the configured product default.
- The eval CLI now dispatches both `A_naive` and `B_hybrid`, records pre-rerank
  RRF and final reranked metrics in one `RunManifest`, supports
  `--reranker/--no-reranker`, and writes a manifest-backed Markdown comparison.
- Streamlit Ask now uses Variant B and sends the configured top 6 chunks to the
  local generator. The eval harness still requests 20 final results, preserving
  a fair comparison with Phase 3.
- `tests/test_phase4.py` — deterministic RRF math/order tests, injected-index
  hybrid-stage tests, and comparison-report provenance tests.

**Acceptance criteria** — met.
- Primary manifest: `reports/phase4_de57151e3ae3.json` (80 examples, same golden
  hash as Phase 3, $0 API cost).
- Before/after report: `reports/phase4_comparison_latest.md`.
- Recall@20 improved from `0.9586734693877551` to `0.9785714285714285`
  (`+0.0198979591836734`).
- MRR improved from `0.49739239518651296` to `0.7855867346938776`
  (`+0.2881943395073646`).
- Precision@20 improved from `0.1007142857142856` to
  `0.10428571428571416`; hit rate held at `0.9857142857142858`.

**Verification**
- `make lint` — passed (`ruff check .`, all checks passed).
- `make test` — passed (`44 passed, 1 skipped`) on the final regression run.
- Streamlit boot — passed; `/_stcore/health` returned `ok` with HTTP 200.
- Real local `B_hybrid` run completed with Ollama `nomic-embed-text` and the BGE
  cross-encoder; the manifest and comparison contain the measured output.

**Deviations from SPEC / honest findings**
- BM25+RRF alone raised MRR to `0.6425166500166504` but slightly lowered
  recall@20 to `0.9571428571428572`. The cross-encoder was not decorative: it
  recovered recall above baseline and lifted MRR again. Both stages remain in
  the report so the mixed RRF-only result is visible.
- Variant B still has partial `RANK_MISS` failures on `gs_003` and `gs_006`.
  Those are global-summary cases and remain direct targets for Variant C graph
  retrieval rather than reasons to tune Phase 4 against the test set.
- The BGE model cache is about 1.1 GB and downloads on first use. Base installs
  can omit the `rerank` extra and run `--no-reranker`, but that RRF-only mode did
  not meet this phase's recall gate.

**Trickiest piece (plain English)**
Dense similarity and BM25 produce scores with unrelated units, so averaging
them would bake in an arbitrary normalization choice. RRF ignores the raw
numbers and rewards agreement in rank position: a document that both systems
place near the top beats one that only one system likes. That improved ordering
substantially, but it also pushed a few relevant documents out of the top 20.
The cross-encoder then read each query-document pair together and recovered
those cases. Keeping pre-rerank and post-rerank metrics in the same run is what
turns that explanation into evidence rather than architecture theater.

**Next:** Phase 5 — structured-output reliability (bounded repair, citation
verification, and a safe abstaining fallback).
