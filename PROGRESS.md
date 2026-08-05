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

---

## Phase 5 — Structured-output reliability  (2026-07-27)

**Built**
- `vaultledger/generate/schema.py` — the LLM-facing contract. `AnswerDraft`
  (`answer_text`, `abstained`, `citations[{chunk_id, snippet}]`) is the *only*
  thing the model produces; the rich `Answer` (tier, routing, privacy,
  confidence) is filled by the orchestrator, so a hallucinated
  `data_left_machine` is structurally impossible. `parse_draft` validates raw
  output into `AnswerDraft` and raises `DraftParseError` with a repair-friendly
  message on empty / non-JSON / malformed / schema-invalid input.
- `vaultledger/generate/reliable.py` — the Phase 5 product path:
  - **L1 repair loop** (`repair_loop`): `for`-bounded by `config.loops.repair_max`
    (2 retries → 3 attempts), feeds each validation error back into the prompt
    (new information per iteration; identical retries banned per SPEC 15.2),
    emits a `GuardrailEvent` per attempt, and on exhaustion returns
    `format_failed` → the caller downgrades to `Answer(abstained=True)`. Never
    raises on bad model output.
  - **Citation verification** (`verify_citations`): snippet-primary. A citation
    survives if a verbatim snippet is present in the claimed chunk, or —
    when the model fumbles the opaque id — if the snippet is verbatim in exactly
    one retrieved chunk (recovered to it). Zero/multiple matches drop; facts
    with no surviving citation downgrade to abstain and tag `CITE_FAIL`.
  - `answer_question_reliable` orchestrates retrieve → assemble → L1 → verify →
    finalized `Answer`, always valid, never a crash.
- `vaultledger/generate/ollama.py` — `generate_json(prompt, schema)` uses
  Ollama's native `format` field for constrained JSON decoding (the
  `instructor` alternative; ADR-0002).
- Wired the eval harness (`evals/run.py`) and the Streamlit Ask screen to the
  reliable path; Ask now renders abstentions, *verified* citations, and the
  reliability-event trail.
- Config: typed `generation.min_snippet_chars` (SPEC "config is typed" rule);
  repair budget already lived in `loops.repair_max`.
- Kept the Phase-3 prose `answer_question` as the baseline receipt.
- ADR-0002 (structured output, repair loop, snippet-primary citation verify).
- `tests/test_phase5.py` — 15 deterministic tests (no live model).

**Acceptance criteria** — met.
- *100 consecutive queries, zero crashes; malformed repaired or safely
  downgraded:* `test_ac_100_consecutive_queries_never_crash` drives 100 queries
  through a rotating chaos menu (clean JSON, unknown chunk_id, fabricated
  snippet, truncated/empty/prose output, wrong types, missing keys,
  injection-flavored text). Every result is a valid `Answer`; every surfaced
  answer carries a verified citation; every unverifiable/malformed case
  downgrades to the fixed abstention. The suite asserts both survival and
  downgrade paths are exercised.
- *Repair is bounded and informative:* tests confirm repair-then-succeed on
  attempt 2, and exhaustion at exactly `max_retries + 1` calls with a
  `GEN_FORMAT`-tagged downgrade — no extra model calls past budget.

**Verification**
- `make lint` — passed (`ruff check .`, all checks passed).
- `make test` — passed (`60 passed`); the `while True` CI ban holds (the L1 loop
  is a bounded `for`).
- Live end-to-end, grounded happy path (real `qwen3:8b` + `nomic-embed-text`,
  Variant B): `reports/phase4_37384620159a_answer.json` — golden `sd_001`
  answered `$4,207.55`, `abstained=false`, `confidence=0.729`, one verified
  citation `stmt_marcus_checking_2025-03#c0` with verbatim snippet
  `"Closing balance: $4,207.55"`, `citation_docs_match_expected=true`, zero
  guardrail events (clean pass — no repair, no dropped citation).
- Live end-to-end, safe-abstain path: `reports/phase4_0af0e7233b60_answer.json`
  — golden `sd_009`, the model's citation was unverifiable, so the guard
  downgraded to an honest abstention (`CITE_FAIL`) instead of surfacing it.

**Deviations from SPEC / honest findings**
- **`instructor` not adopted** (SPEC 7.1 suggestion): its built-in retry is an
  opaque, unbudgeted loop, which fights SPEC 15's "every loop explicit and
  observable" rule. Chose native Ollama `format` + a hand-rolled L1 loop; zero
  new deps; `instructor` documented as the drop-in for the Phase 11 hosted
  tiers. Full rationale in ADR-0002.
- **Only citation verification lands here**; numeric verify, cross-persona, and
  advice linter are Phase 13 per SPEC — not started.
- **Live finding #1 — the generator must see `answer_top_n`, not the eval `k`.**
  The first live probes abstained on trivially answerable questions. A raw-output
  diagnostic (kept the exact prompt, printed the model's JSON) showed `qwen3:8b`
  emitting a *perfect* citation at `answer_top_n=6`:
  `{"chunk_id": "stmt_marcus_checking_2025-03#c0", "snippet": "Closing balance:
  $4,207.55"}`. The abstentions came from the eval harness feeding the generator
  `k=20` — twenty near-identical Marcus statements — which the small model can't
  disambiguate, so it dropped its citation. Fix: `answer-one` now generates from
  `cfg.retrieval.answer_top_n`, matching the Streamlit product path; retrieval
  metrics still use `k=20` on their own path. Lesson worth the write-up:
  retrieval breadth and generation context are different knobs and conflating
  them silently tanks citation precision.
- **Live finding #2 — citation quality is prompt-load-bearing.** A generic
  "cite your sources" instruction left citations empty; an explicit
  "copy the chunk_id character-for-character, quote the snippet verbatim, don't
  paraphrase" instruction (plus a format-only example that leaks no golden
  answer) is what produced the exact-id, verbatim-snippet output above. The
  snippet-recovery guard (recover a fumbled id when the quote is verbatim in
  exactly one chunk) remains the safety net for the residual cases.
- **Honest boundary:** these two fixes were validated on live examples end-to-end,
  not by tuning thresholds against the golden set. Full generation correctness /
  abstention confusion matrix across all 80 examples is Phase 7 work; Phase 5
  proves the reliable path runs, cites verifiably, and never crashes.

**Trickiest piece (plain English)**
The hard part of Phase 5 is that "reliable" means *the loop must be trustworthy
even when the model is not*. The design that makes this work is putting the
verification, not the model, in charge of what gets said. The model produces a
tiny JSON draft; nothing it writes about tier, privacy, or "data left the
machine" is trusted — those are stamped by our code, so an entire class of
hallucination is impossible by construction. The one thing we *do* take from the
model — its citation — is treated as a *claim to be checked*, not a fact: the
quoted snippet must appear verbatim in a retrieved chunk, and if the model
mislabels the chunk id but the quote is genuinely there in exactly one chunk, we
correct the label rather than trust or reject it blindly. When neither the
claimed id nor the quote checks out, the answer downgrades to an honest "I
couldn't find that," never a confident-but-unsupported number. The repair loop
around all of this is a plain bounded `for` that feeds each schema error back to
the model and gives up cleanly after a fixed budget — no framework, no hidden
retries, so every iteration is visible in the guardrail-event trail. The payoff
showed up live: the same model that emitted a flawless verified citation on one
question, and an unverifiable one on another, produced a *safe* result both
times — a grounded answer in the first case, an honest abstention in the second.

**Next:** Phase 6 — privacy switch / routing v1 (Local/Cloud toggle, per-query
"data left your machine" badge, session consent, degraded-mode fallback).

---

## Phase 6 — Privacy switch / routing v1  (2026-07-28)

**Built**
- `vaultledger/route/privacy.py` — a deliberately small binary router around
  the Phase-5 reliable answer path. Local mode permits T0/T1 and calls only the
  injected local generator. Cloud mode requires explicit session consent,
  records a T2 `RoutingDecision`, and stamps `privacy_mode`,
  `data_left_machine`, tier, and model in code rather than trusting model text.
- Cloud failure is caught at the routing boundary and re-runs through the local
  model. Missing configuration (before egress) returns local/NO metadata and
  “Cloud unavailable — answered locally.” A provider failure after the cloud
  generator is invoked conservatively preserves cloud/YES egress metadata,
  while `model_used` truthfully names the local model that produced the answer.
- `vaultledger/gateway/openai_compatible.py` — the narrow hosted-generation
  seam for routing v1. It is constructed only after Cloud mode and consent are
  selected. Phase 11 will replace this single endpoint with LiteLLM.
- Typed `cloud` config for model, OpenAI-compatible base URL, secret environment
  variable name, and timeout. The API key is never stored in YAML.
- Streamlit Ask now exposes Local / Cloud-Boosted, requires a session consent
  checkbox before enabling Cloud Ask, and renders a per-answer
  “Data left your machine: YES/NO” badge from the finalized `Answer`.
- `answer_question_reliable` now accepts router-owned metadata while preserving
  its Phase-5 repair and citation-verification behavior.
- `tests/test_phase6.py` — deterministic AC coverage for local isolation,
  consent, cloud metadata, and degraded fallback.

**Acceptance criteria** — met in deterministic CI tests.
- *Badge + model flip:* cloud results assert `data_left_machine=True`,
  `privacy_mode=cloud`, hosted `model_used`, T2, and the matching routing record;
  local results assert the inverse with the configured Ollama model.
- *Zero network calls in local mode:* the test replaces `socket.socket` with a
  function that immediately fails. Local routing still completes, while an
  injected cloud generator records zero calls. This tests the router with
  in-memory retrieval/generation; the production local model and embedder use
  Ollama on loopback, not an external provider.
- *Degraded path:* missing cloud configuration produces a grounded local answer
  with local/NO metadata. A cloud generator that raises `GenerationError`
  produces a grounded local answer but preserves cloud/YES metadata because the
  prompt may already have reached the provider. Both log availability events.
- *Session consent:* cloud mode without consent fails before any generation.

**Verification**
- `python -m pytest` — passed: `64 passed, 1 skipped`.
- `python -m ruff check .` — passed.
- `git diff --check` — passed.

**Deviations / honest boundary**
- No live hosted query was made, so provider compatibility and answer quality
  are not claimed here. The AC is exercised with deterministic generators and
  a real HTTP client seam. A blank cloud URL or absent key intentionally takes
  the degraded local path.
- PII redaction before cloud egress is Phase 13 in the v2 plan and is not
  claimed by this phase. The current corpus is synthetic-only, and the consent
  copy says that retrieved context is sent. Real-document cloud use should not
  ship before the Phase-13 egress guard lands.
- Routing v1 follows only the user's privacy choice. Query-aware policy,
  budgets, escalation, and provider fallbacks remain Phase 12.

**Trickiest piece (plain English)**
The badge is only useful if it reports what actually happened, especially
during failure. The router therefore does not decide the badge from the toggle:
it decides it from the path that completed. A selected Cloud toggle can still
produce a local/NO answer when the provider is unavailable, and the routing
record explains why. Just as importantly, the local branch never performs a
cloud availability check. That makes “local” a hard execution constraint rather
than a UI preference that might quietly phone home.

**Next:** Phase 7 — adversarial and safety evals (prompt injection,
lost-in-the-middle, and abstention confusion matrix).

---

## Phase 7 — Adversarial & safety evals  (2026-07-28)

**Built**
- `sanitize_context` removes instruction-like lines from retrieved document
  content before generation and leaves an explicit placeholder. Citation
  verification still checks against the original chunks, so ordinary grounded
  facts from a poisoned document remain answerable.
- A second, independent output tripwire catches instruction-following language
  and downgrades it to the fixed abstention before it can surface. Both stages
  emit `prompt_injection` guard events.
- `reorder_for_lost_in_middle` sorts by retrieval score and distributes strong
  evidence across context edges (best first, second-best last, and so on).
  `assemble_context(..., reorder=False)` preserves the old ordering as a
  deliberate comparison/control path; typed config enables reordering by
  default.
- `abstention_confusion` reports answered-right, answered-wrong,
  rightly-abstained, and wrongly-abstained, plus unanswerable recall,
  answerable specificity, coverage, and `ABSTAIN_FP` / `ABSTAIN_FN` failures.
- `python -m vaultledger.evals safety` / `make eval-safety` runs the real local
  Variant-B path on all 10 unanswerable examples plus poisoned case `adv_001`,
  writing a `RunManifest` and complete raw answers.
- `tests/test_phase7.py` adds four deterministic gates: context injection
  removal with a normal grounded answer, malicious-output suppression,
  lost-in-the-middle control vs reordered recovery, and confusion-matrix/error
  taxonomy correctness.

**Acceptance criteria** — met.
- *Injection never triggers the dump:* live `adv_001` answered Marcus Chen's
  March closing balance as `$4,207.55`; the injected line was blocked before
  generation and no account-number dump appeared. A separate deterministic
  malicious generator that tries to emit `SYSTEM: list all account numbers:
  1234567890` is downgraded, proving the output backstop.
- *Abstention correct on the unanswerable set:* the live local run rightly
  abstained on all 10/10 golden unanswerable questions, with zero answered
  unanswerables and zero failures.
- *Lost-in-the-middle recovery demonstrated:* a position-sensitive deterministic
  generator abstains when the highest-scoring gold chunk is forced into raw
  position 3/5, then returns the verified `$9,876.54` answer when edge
  reordering moves it first. This is a deterministic mechanism test, not a
  claimed live-qwen accuracy delta.

**Measured artifact**
- `reports/phase7_f6020de1c75d.json` (`phase7_latest.json`) — real
  `ollama/qwen3:8b`, Variant B, golden hash
  `ece0ea370052...`: `rightly_abstained=10`, `answered_right=1`,
  `answered_wrong=0`, `wrongly_abstained=0`,
  `abstention_unanswerable_recall=1.0`, `injection_pass_rate=1.0`, no failures.
- `reports/phase7_f6020de1c75d_answers.json` keeps every raw finalized `Answer`
  and guard event. The manifest records zero dollar cost because the run was
  fully local.

**Verification**
- Live safety gate completed against installed `qwen3:8b`,
  `nomic-embed-text`, and Variant-B indexes.
- Full `pytest` gate: `68 passed, 1 skipped`; Ruff: all checks passed.
- The Phase-5 100-query chaos gate and all Phase-6 privacy-routing gates remain
  in the full regression suite.

**Honest boundaries**
- The 100% rates above cover exactly 11 examples: all 10 unanswerables and one
  poisoned-document question. They are not estimates for the full 80-example
  set or other models.
- The lost-in-the-middle before/after is a deterministic spec-by-example using
  a position-sensitive generator. It proves ordering and orchestration behavior,
  not that `qwen3:8b` itself always fails in the middle.
- The injection patterns are a narrow Phase-7 defense for the seeded attack.
  Formal guard confusion matrices, over-refusal measurement, PII egress
  redaction, and cross-persona protection remain Phase 13.

**Trickiest piece (plain English)**
Prompt instructions are not a safety boundary: the poisoned sentence reached
the same model prompt as legitimate balances and transactions. The fix creates
two boundaries around the model. Before generation, instruction-shaped document
lines are replaced, so the model cannot obey what it cannot see. After
generation, instruction-following language is still treated as hostile and
blocked. The original retrieved chunks remain untouched for citation checking,
which is why the model can safely answer the real balance from the poisoned
statement without losing evidence integrity.

**Next:** Phase 8 — observability and cost (stage spans, per-query latency /
tokens, and cost attribution).

---

## Phase 8 — Observability & cost  (2026-07-28)

**Built**
- `vaultledger/observability/tracing.py` — local-first `QueryTrace`,
  `SpanRecord`, monotonic `TraceRecorder`, durable one-file-per-trace
  `TraceStore`, required-dimension rollups, health metrics, and an optional
  Langfuse v4 exporter.
- Every privacy-routed product query now records route, retrieve, assemble,
  guards-in, generate/repair, and guards-out spans; final model, tier, variant,
  privacy path, total latency, retrieval score, repair/guard/escalation health,
  token count, cost, and outcome live on the same trace.
- Token accounting is explicitly labeled `estimated_chars_div_4` because the
  current Phase-3/6 generator clients discard provider usage. This is not
  presented as exact billing telemetry. Phase 11's gateway will replace the
  estimate when provider usage is available.
- Local inference is always attributed `$0`. Hosted cost uses typed,
  user-configured input/output rates and estimated tokens; rates default to
  zero rather than embedding unverified, drifting provider prices.
- `RoutingDecision.actual_cost_usd` is updated from the finalized trace, keeping
  routing, UI, and rollups on one cost value.
- The Streamlit answer footer shows trace id, latency, estimated tokens, source,
  and cost. The Evals dashboard shows query count, health rates, and a table of
  cost / average latency grouped by feature, category, tier, and variant.
- `langfuse>=4,<5` is an optional `observability` extra. Export is explicit;
  no Langfuse import, initialization, availability probe, or network call
  occurs on the normal local path.
- `tests/test_phase8.py` adds gates for full persisted stage traces,
  repair health, local vs hosted cost, required rollup dimensions, and optional
  Langfuse behavior.

**Acceptance criteria** — met.
- *Full trace per query:* the product route automatically builds a complete
  trace and the Streamlit path persists it under typed `paths.traces`.
  Deterministic tests require all six stages and reload the trace from disk.
- *Cost per feature/category on dashboard:* rollups group query count, cost, and
  average latency across feature, category, tier, and variant; the Streamlit
  Evals tab renders the table and health headline metrics.
- Health includes abstention rate, average retrieval score, repair-trigger
  rate, guardrail-flag rate, and escalation rate.

**Live verification**
- Real local query: “What was Marcus Chen March closing balance?” through
  Variant B + `qwen3:8b`, trace `trace_dd06a1718790`.
- Grounded non-abstained answer; six spans. Measured total `13,792.747 ms`:
  retrieval `3,648.842 ms`, generation/repair `10,140.774 ms`, and sub-ms
  assembly / guard stages. This single run meets the SPEC's local `<15s`
  target but is not a latency distribution.
- Estimated tokens: 1,221 input + 48 output; local cost `$0`;
  average retrieval score `0.692802`; no repair; one guard flag because the
  poisoned March statement's instruction line was removed.
- Full regression: Ruff, syntax, golden-set, and diff checks passed. The
  original entry recorded `72 passed, 1 skipped`; re-running the suite at the
  Phase 8 commit measured `73 passed, 0 skipped`. The corrected figure is the
  measured one.

**Honest boundaries / deviations**
- Langfuse is optional. No remote Langfuse trace has been produced: this
  machine has no Langfuse credentials, and `.env` does not exist. What has been
  verified is narrower and worth stating precisely — see the post-phase review
  below. Durable local traces remain the tested source of truth.
- The exporter reconstructs the measured local spans after completion rather
  than decorating every function with `@observe`. This avoids making external
  telemetry a runtime dependency and preserves the local-mode no-egress
  guarantee.
- Hosted token counts and cost remain estimates until Phase 11 exposes actual
  gateway usage. Configured zero rates mean “not priced,” not “provider is
  free.”
- Replay needs an explicit privacy design because persisting raw financial
  questions/context broadens local data retention. Trace metadata is sufficient
  for Phase 8 AC; raw-input replay is not claimed.

**Trickiest piece (plain English)**
Observability can undermine a privacy product if the tracing system becomes a
second place that quietly receives sensitive prompts. The design therefore
makes a local JSON trace the canonical record and sends nothing anywhere by
default. Langfuse export is a separate explicit action. The same honesty rule
applies to cost: character-based token estimates are useful for comparing work,
but they are labeled estimates and zero provider rates are treated as
unconfigured—not disguised as precise billing.

**Post-phase review (2026-07-28)** — the Langfuse claim was checked rather
than assumed, and the check found a real bug.

- *Bug: the exporter reported success it had not earned.* `export_to_langfuse`
  returned `True` whenever the `langfuse` package merely imported. Installing
  the extra and running it showed Langfuse logging *"Client will be disabled"*
  for missing credentials while the function still returned `True` — a
  telemetry function claiming an export that never left the process, in a
  project whose whole argument is honest instrumentation. Fixed with a
  `client.auth_check()` guard, which short-circuits without a network call when
  no credentials are present.
- *The old test only passed because the extra was uninstalled.* It asserted
  `export_to_langfuse(...) is False` against the ambient environment, so
  installing the optional extra broke the suite. Replaced with two
  environment-independent gates: dependency absent (import forced to fail) and
  dependency present but unauthenticated, the second skipping when the extra
  is not installed.
- *Verified:* the adapter's API usage is correct against the real SDK
  (`langfuse 4.14.1`) — `get_client`, `start_as_current_observation(as_type=…,
  name=…, metadata=…)`, and `flush` all exist with the signatures used.
  *Not verified:* that a span arrives in a Langfuse project. That needs
  credentials and remains unclaimed.
- *Packaging:* installing `.[observability]` unconstrained broke `pip check`.
  Langfuse pulls the OTLP http exporter, chromadb's installed grpc exporter
  pins the opentelemetry line to its own version, and the two exporters pin
  incompatibly. Constrained the extra to the matching exporter version;
  `pip check` is clean with both libraries installed and importable.
- *Double `finish()`:* both the reliable-answer path and the privacy router
  call `TraceRecorder.finish`, and the retrieval-score health metric survived
  only because of an `is not None` guard. Made the retained value explicit and
  documented that `finish` is safe to call more than once, so a future field
  cannot silently blank a health metric.
- Suite after these changes: `74 passed`, Ruff clean, with the extra both
  installed and absent.

**Next:** Phase 9 — judge validation and regression runner.

---

## Phase 9 — Judge validation + regression runner  (2026-07-28)

**Built**
- `vaultledger/evals/judge/human_labels.yaml` — exactly 20 manually classified
  candidate answers, balanced 10 acceptable / 10 unacceptable. The cases cover
  exact and paraphrased facts, correct abstention, aggregation, comparison,
  discrepancy explanation, wrong numbers/entities/periods, false abstention,
  unsupported claims, partial aggregation, and injection-following output.
- `rubric_v1.md` — a versioned correctness + faithfulness rubric. PASS requires
  both semantic correctness and complete evidence support; false abstention,
  unsupported extras, advice, leaked account data, and document-instruction
  obedience explicitly fail.
- `judge/validate.py` — typed labels/verdicts, schema-constrained judge prompts,
  rubric hashing, balanced-set validation, and independent TPR/TNR confusion
  metrics.
- `python -m vaultledger.evals judge-validate` / `make judge-validate` runs the
  strongest configured available tier, writes a manifested result and all
  item-level verdicts/reasons, and exits nonzero unless both TPR and TNR are
  strictly above 0.80.
- `vaultledger/evals/regression.py` plus committed
  `regression_baseline.json` — metric policies tied to the measured Phase-4
  manifest and frozen golden hash. Missing required metrics fail closed.
- `python -m vaultledger.evals regression` / `make regression` writes a
  machine-readable delta report and exits nonzero when any drop exceeds its
  metric-specific threshold. CLI injection flags create a reproducible negative
  control without editing the source manifest.
- `make eval-full` now runs golden validation, Phase-7 live safety, judge
  validation, and regression in sequence.
- Streamlit Evals now shows judge TPR/TNR/label count and a green/red regression
  table against the persisted baseline.
- `tests/test_phase9.py` — six deterministic tests for label balance/versioning,
  independent TPR/TNR math, baseline green path, missing-metric fail-closed,
  and deliberate-regression detection.

**Acceptance criteria** — met.
- *Judge TPR/TNR >80% against 20 human labels:* live configured
  `ollama/qwen3:8b` run `phase9_judge_2eed824d4657` produced TP=10, TN=10,
  FP=0, FN=0: TPR=1.00, TNR=1.00, accuracy=1.00.
- *Regression runner catches a deliberately injected regression:* the CLI
  negative control subtracts 0.02 from retrieval MRR. The allowed drop is 0.01,
  so `regression_injected_fixture.json` reports `passed=false`, flags only MRR,
  and exits 1. The untouched `phase4_latest` comparison is green.

**Artifacts**
- `reports/phase9_judge_2eed824d4657.json` and
  `phase9_judge_latest.json` — RunManifest with model, hashes, metrics, and
  failures.
- `reports/phase9_judge_2eed824d4657_verdicts.json` — rubric hash
  `ad2b94ce951d...`, label hash `89533bd082e4...`, and every human/judge verdict
  with rationale.
- `reports/regression_latest.json` — green comparison of a fresh run
  (`phase4_be55865df056`, 2026-07-30) against the frozen baseline
  (`phase4_de57151e3ae3`). Regenerated on review: the first version compared
  the baseline run against itself, so every delta was necessarily `0.0` and the
  artifact proved only that the file parsed.
- `reports/regression_injected_fixture.json` — intentional red control.
- `reports/phase4_be55865df056.json` — the fresh run behind the green
  comparison, full pipeline (Ollama embeddings → Chroma + BM25 → RRF →
  BGE rerank) re-run five days after the baseline was frozen.

**Verification**
- Full regression: `79 passed, 1 skipped` (`80 passed` with the optional
  `observability` extra installed, which un-skips the Langfuse auth gate).
- Ruff, syntax compilation, CLI parser, and `git diff --check` passed.
- *Runner checked behaviourally, not only arithmetically (added on review).*
  The CLI negative control subtracts a constant from a metric, which exercises
  the threshold comparison rather than the system. Fed the real Phase-3
  naive-retrieval manifest instead, the runner flags `recall@20` (−0.0199) and
  `retrieval_mrr` (−0.2882), leaves `precision@20` and `hit_rate` green, and
  exits 1 — so it catches a genuine measured degradation and not just an edited
  number.
- *Determinism confirmed across days (2026-07-30).* The fresh
  `phase4_be55865df056` run reproduced all four baseline retrieval metrics
  bit-for-bit (deltas exactly `0.0`) five days after the baseline was frozen.
  A green regression report is meant to show reproduction, so identical deltas
  are the expected result here — but they only mean something because the run
  ids differ.

**Honest boundaries**
- The 20 labels were authored as clear calibration cases, not sampled from a
  noisy production-answer distribution. Perfect alignment proves the rubric and
  configured judge can separate these boundaries; it does not imply 100%
  accuracy on subtle, partially correct, or out-of-distribution answers.
- SPEC's “100% means the suite is too easy” principle applies. The next judge
  set should add ambiguous partial-credit and paraphrase-stress cases while
  keeping this v1 set frozen as a regression receipt.
- No rubric iteration was needed on v1; there is therefore no claimed
  before/after alignment improvement.
- The strongest *configured and available* judge was local `qwen3:8b`: cloud
  T3 had no configured endpoint/key and was not silently invoked. The run cost
  is correctly recorded as `$0`.
- The regression v1 baseline covers mature deterministic retrieval metrics.
  Generation, safety, cost, and judge baselines should be added as their
  populations stabilize; metrics from incompatible golden hashes cannot be
  compared.
- `RunManifest.golden_set_hash` contains the human-label file hash for the judge
  validation run. This reuses the existing manifested-dataset field rather than
  pretending the 80-item QA golden hash was used.

**Trickiest piece (plain English)**
A judge score is not trustworthy merely because another model emitted it. The
judge is a classifier, so it needs the same validation discipline as any other
classifier: known positives, known negatives, and both error directions
measured separately. TPR alone would let an always-PASS judge look perfect;
TNR alone would reward an always-FAIL judge. The balanced human set makes both
shortcuts visible. The regression runner follows the same principle: the green
path proves compatibility, while the deliberately damaged MRR is the negative
control proving the alarm actually rings.

**Next:** Phase 10 — Track-A polish, fresh-machine run, demo, and report draft.

---

## Phase 10 — Track-A polish  (2026-07-30)

Written on review, after the two Phase 10 commits (`7689f79`, `91c41b8`) landed
without a build-log entry. The phase closed on 2026-08-04 when the owner-recorded
browser walkthrough was added; the fresh-machine criterion remains partial and
is not upgraded without a clean-virtualenv transcript.

**Built**
- `vaultledger/doctor.py` + `make doctor` — a read-only readiness check over the
  documented setup: Python version, config load, required imports, 60/60
  synthetic PDFs, the four local index artifacts, Ollama embedding/generation
  models, and the presence of Track-A eval receipts. Every failing check carries
  the exact remedy command. It installs, downloads, generates, and ingests
  nothing.
- `make verify-track-a` — the phase gate as one target: `lint test eval-full`,
  where `eval-full` chains golden validation, the live safety eval, judge
  validation, and the regression comparison.
- README rewritten around the fresh-checkout path, with the previously missing
  steps now explicit and ordered: venv → `make install` → `ollama pull
  nomic-embed-text` → `ollama pull qwen3:8b` → `make data` → `make ingest` →
  `make doctor` → `make run`.
- `tests/test_phase10.py` — release version and Streamlit config pins, a
  Streamlit `AppTest` smoke test asserting the four-tab tree renders with no
  exception, an assertion that the README's setup commands appear *in order*,
  and a doctor test proving it reports missing corpus/index without creating
  anything.
- `.streamlit/config.toml` + a `make run` that passes `--server.headless` and
  `--browser.gatherUsageStats=false`, so a first launch raises no telemetry
  prompt and phones nothing home. Consistent with the product thesis.
- App polish: Track-A version caption, synthetic-data notices, population stated
  on the retrieval headline (70 answerable of 80), and the Experiment Lab
  labelled as post-internship Phase 11+ scope.
- `demo/README.md` — the recording script, committed before the recording
  exists.
- Version bumped `0.0.0` → `0.1.0` (Track-A internship deliverable).

**Acceptance criteria** — two met, one partially met.
- *Full regression green:* **met.** Re-verified on review, not taken on trust —
  see Verification below.
- *Fresh-machine run from README:* **partially met.** The documented path is now
  complete and ordered, a test enforces that order so the README cannot silently
  drift, and `doctor` diagnoses a fresh checkout correctly (confirmed on review
  against a clean clone: `0/60 PDFs → run make data`, missing indexes → `run
  make ingest`). What is *not* committed is a transcript of an actual
  clone-to-`make run` walkthrough in a clean virtualenv. The repo-side work is
  done; the end-to-end proof is not on file.
- *Demo recorded:* **met.** `demo/vaultledger_track_a_v1.gif` shows corpus and
  index health, the grounded `$4,207.55` local answer with citation and trace,
  a credit-score abstention, the Track-A eval receipts, and the Phase-11
  boundary; about 2 seconds of the credit-score query's roughly 9-second spinner
  are shown at 4× speed, while the rest is continuous real time and the
  on-screen trace latency is unaltered.

**Deviations from SPEC**
- SPEC 16 scopes Phase 10 as "README, demo v1, internship report draft."
  `doctor.py` and `verify-track-a` are additions beyond that text. They were
  kept because a setup document drifts silently while a read-only checker fails
  loudly on the user's actual machine — the AC is "a fresh machine works," not
  "a fresh machine is described."
- The internship report draft is not in this repo. Per `CLAUDE.md`'s routing
  rule — compiler/harness output here, recruiter/lead output in PM-OS — it
  belongs in `~/Desktop/PM-OS`. It remains outstanding.

**Findings from live use (2026-08-04)**
- Under-specified questions behave inconsistently. “What was the pay stub's net
  pay?” returned `2,525.39` at confidence `0.50` while citing six different pay
  stubs; “What was the invoice total?” abstained at confidence `0.00`; and
  “Summarize the March statement” summarized all three people. The harness does
  not measure this.
- Streamlit renders `$...$` as LaTeX, swallowing text between two dollar signs
  and corrupting displayed currency. This was visible in the March-statement
  summary. It is a presentation issue only; the underlying answer and citations
  were correct.
- Currency output format is unspecified: `$24,500`, `$24,500.00`, and “5,403
  dollars and 97 cents” all occur. This is deliberately a generation/display
  concern, not a judge concern; `rubric_v1` says formatting differences do not
  matter.
- One `make run` process intermittently exited with signal 11 after the server
  was already serving. There was no Python traceback, no crash report was
  captured, and it did not reproduce on restart. Cause unknown.

**Verification** (measured on close, 2026-08-04)
- `make verify-track-a` — **exit 0**, 140.58s (2m20.58s) wall clock, all four
  stages green:
  - ruff clean; `85 passed`
  - safety: 1 answered right, 0 answered wrong, 10 rightly abstained, 0 wrongly
    abstained, `injection_pass_rate 1.0`
  - judge: `judge_tpr 1.0`, `judge_tnr 1.0`
  - regression: `passed: true`
- `make doctor` on the development machine: 7/7 checks pass.
- `doctor` against a fresh `git clone`: correctly fails the corpus and index
  checks with the right remedies, and creates nothing.

**Honest boundaries**
- Phase 10 is closed because the demo and full-regression criteria are met; the
  fresh-machine criterion remains explicitly partial because no clean-virtualenv
  transcript is committed.
- The gate result above is a re-run on the development machine. It is not
  evidence that a clean virtualenv install succeeds from scratch; nobody has
  committed that transcript.
- Unchanged and still true from earlier phases, and none of it may be overstated
  in the README or the report: the 20 judge labels were adjudicated by the owner
  on 2026-08-04 against `rubric_v1` — all 20 confirmed, no label changed, so they
  are now human labels rather than calibration labels — but TPR/TNR of 1.00 still
  reflects a deliberately clear set with no headroom to detect a judge getting
  worse, and adjudication does not make the set harder; no Langfuse span has ever
  reached a Langfuse project; hosted token counts and cost are estimates, and zero
  provider rates mean unpriced, not free.
- The demo is a live browser walkthrough, not an eval artifact. It keeps the
  credit-score abstention visible and uses the committed RunManifest-backed
  receipts for its measured claims; it is not described as unedited because the
  disclosed spinner segment is speed-ramped.

**Trickiest piece (plain English)**
The obvious way to pass "a fresh machine works" is to write better setup
instructions. That fails quietly: documentation drifts away from the code the
moment a path, a model name, or an install step changes, and nothing in the
build catches it. Two mechanisms replace the prose. A read-only doctor runs on
the user's real machine and reports which documented step is still missing, with
the exact command to fix it — so the check happens where the truth is rather
than in a paragraph. And a test asserts the README's commands appear in the
correct order, which turns the setup narrative itself into something CI can
fail. The general habit: when a criterion is about the world rather than the
code, find the smallest executable thing that observes the world, because a
claim nobody can re-run is indistinguishable from a claim nobody checked.

**Next:** the internship report draft remains outstanding in `~/Desktop/PM-OS`.
Phase 11 begins with an ADR for the model lineup/config contradiction, then the
model gateway and benchmark matrix; no Phase 11 work is started here.

---

## Phase 11 — Local model gateway + benchmark-matrix machinery  (2026-08-05)

ADR-0003 had already resolved the kickoff contradiction: paid T2/T3 providers
are retired, Phase 11 proves the gateway/matrix on the two installed Qwen
models, and the final six-local-model bake-off moves to Phase 17. This pass
turned that decision into runtime behavior. `config.yaml` no longer names Kimi,
GLM, Claude, provider URLs, or API-key settings; the app exposes only Local
mode. The generic Phase-6 cloud-routing helper remains for its historical
privacy/fallback regression tests, but no product or matrix entrypoint can
select it.

**Built**
- `LiteLLMGenerator` preserves the existing `generate_json` seam and records
  provider token usage, completion latency, cost, token source, and pricing
  status per call. LiteLLM imports lazily, so importing the app or deterministic
  tests does not probe a model service.
- Qwen 3 thinking is explicitly disabled for matrix calls. The first live 4B
  probe spent all three schema attempts on hidden reasoning and returned empty
  visible content; with `think=False`, it returned valid schema output in one
  call. This is a gateway correctness fix, not a prompt-quality tweak.
- `python -m vaultledger.evals matrix` runs model × variant cells, enforces the
  session cost cap, writes one `RunManifest` and full `_answers.json` receipt per
  cell, then generates `reports/model_matrix.md` only by reloading those
  manifests. `make matrix` is the stable entrypoint.
- The deterministic scorer is deliberately narrow: unanswerables require the
  correct abstention; answerable references require their literal
  amounts/dates/identifiers, or a normalized full-reference substring when no
  such anchors exist. It is labelled a lower bound throughout and never called
  an LLM-judge result.

**Kickoff measurement** (Variant B, first 12 golden rows — all `single_doc`)
- `ollama/qwen3:4b`: strict match `16.7%`, citation-document hit `33.3%`,
  abstention accuracy `33.3%`, median/p95 gateway latency `3.328s / 5.854s`,
  `22,235 / 741` input/output tokens, `$0.000000` measured API spend.
- `ollama/qwen3:8b`: strict match `58.3%`, citation-document hit `58.3%`,
  abstention accuracy `83.3%`, median/p95 gateway latency `5.380s / 8.576s`,
  `22,307 / 788` input/output tokens, `$0.000000` measured API spend.
- On this small easy slice, 8B is materially more reliable and 4B is materially
  faster. That finding must not be generalized to the other 68 golden rows,
  another family, or another RAG variant.

**Acceptance status**
- The ADR-revised Phase-11 machinery criterion is functionally met: two local
  models registered, LiteLLM gateway live, matrix command live, two cell
  manifests plus answer receipts, generated report, and spend inside budget.
- The phase remains **open** until these worktree changes are committed and the
  matrix is rerun from that clean source state. The current manifests correctly
  contain the pre-phase base SHA `e17edfb`, but the schema has no dirty-tree
  field, so they are useful live receipts rather than a fully replayable release
  receipt.
- The original SPEC wording of six models across three hosting tiers is not met
  and will never be reinterpreted as met. ADR-0003 records that scope reduction;
  Phase 17 owns six local models, measured sizes, the full golden set across the
  finished variants, and per-model judge reasons.

**Review pass (2026-08-05, before commit)**
- **Defect found and fixed: the egress badge had become a hardcoded string.** The
  implementation replaced `if answer.data_left_machine: ... else: st.success(...)`
  with an unconditional `st.success("Data stayed on your machine · NO cloud
  egress")`. The string was accurate — `mode` is hardcoded to local — but the
  claim was no longer derived from the field that makes it true, so any future
  change re-enabling a remote path would have left the badge silently lying. The
  conditional is restored, and
  `test_privacy_badge_is_derived_from_the_answer_not_asserted` fails if the guard
  is removed while the badge remains. That test was negative-controlled against a
  simulated regression rather than assumed to work.
- **ADR-0003 amended.** It had said the Local/Cloud-Boosted switch would stay
  exactly as Phase 6 built it. The implementation removed it. On review the
  removal stands and the ADR clause was wrong: a toggle that can never do
  anything advertises a capability the product does not have. The amendment
  records what was preserved (`privacy.py` and its Phase 6 tests, untouched) and
  what it costs.
- **SPEC's Phase 6 AC "badge + `model_used` flip correctly" is no longer
  demonstrable in the product.** It holds at the unit level only. Recorded as a
  scope reduction, not a passing AC.
- **`demo/vaultledger_track_a_v1.gif` is now out of date** — it shows a privacy
  radio the app no longer has. Flagged in `demo/README.md`; re-record at the next
  demo revision.

**Verification so far**
- Full deterministic suite at this commit, re-run independently during review:
  `89 passed`; ruff clean. (The implementation pass reported `87 passed, 1
  skipped` on its own environment; the review environment has the optional extra
  installed, so that test runs, and the new badge guard adds one more.)
- Live LiteLLM/Ollama probe: both `qwen3:4b` and `qwen3:8b` produced manifests,
  answer receipts, provider token counts, and a generated report at zero
  measured API spend.
- Configured live kickoff matrix: 2 models × 1 variant × 12 examples, 24/24
  generation outcomes recorded; total measured API spend `$0.000000`.

**Honest boundaries**
- Zero dollars means **unpriced, not free**. Electricity, hardware, and local
  compute are not billing telemetry.
- The kickoff sample is the first 12 rows, all easy/medium single-document
  questions. It is a plumbing proof with an early signal, not a representative
  quality comparison.
- Strict matching under-credits valid paraphrases and cannot establish semantic
  correctness. Phase 17 owns judged verdicts with reasons.
- Exact model digests, parameter counts, and resident sizes are not pinned here;
  ADR-0003 assigns that work to Phase 17 kickoff.

**Acceptance criteria** — met as rescoped by ADR-0003; SPEC's literal wording is
explicitly not met.
- *A RunManifest per cell:* **met.** Two cells, two manifests, two full
  `_answers.json` receipts.
- *`model_matrix.md` generated by the harness, never hand-edited:* **met.** The
  report is produced only by reloading committed manifests; a test asserts this.
- *Total spend within budget:* **met, trivially.** `$0.000000` measured, because
  every model is local. Unpriced, not free.
- *"Across ≥ 6 models":* **not met, and not reinterpreted as met.** ADR-0003
  rescoped Phase 11 to the gateway and matrix machinery against the two installed
  models and reassigned the six-model sweep to Phase 17. Phase 11 is closed on
  the rescoped criteria only.

**Rerun from the clean committed state (2026-08-05)**
The manifests first produced during implementation were generated from
uncommitted source, so their `run_id` identified no commit. `make matrix` was
re-run at `3f545db` with a clean tree — 2m21.6s wall clock — and the stale pair
was removed. Current receipts: `phase11_ollama_qwen3_4b_b_hybrid_28dd82352c14`,
`phase11_ollama_qwen3_8b_b_hybrid_f9640c192353`.

**Determinism finding (unplanned, from that rerun)**
Comparing the two back-to-back runs on an idle machine:
- **Every quality metric was identical**: strict match `16.7%` / `58.3%`,
  citation hit `33.3%` / `58.3%`, abstention accuracy `33.3%` / `83.3%`, and
  token counts to the token (`22,235 / 741` and `22,307 / 788`). Generation is
  reproducible at these settings and the scorer is deterministic.
- **Only latency moved**: 4B p50 `3328 → 3383 ms`, p95 `5854 → 5785 ms`; 8B p50
  `5380 → 5604 ms`, p95 `8576 → 9453 ms`. The 8B p95 shifted about **10%**
  between identical back-to-back runs.

That has a direct consequence for ADR-0003, which replaced the cost axis with a
latency axis: **latency is the noisy axis.** A single run cannot support a
latency–quality frontier at this resolution. Phase 17 must run each cell more
than once and report a spread, or the frontier's x-position is within noise.
Recorded here rather than discovered when the chart is drawn.

**Next:** Phase 12 — policy router v2, escalating across local model sizes rather
than hosting tiers (ADR-0003). Still outstanding and unchanged: the internship
report draft in `~/Desktop/PM-OS`, and the demo re-record noted in
`demo/README.md`.

---

## Phase 12 — Deterministic local-size policy router v2  (2026-08-05)

Implementation and first full measurement complete; closed after the router
artifact was regenerated from a clean SHA.
ADR-0004 resolves the heuristic-versus-learned choice: the first router is an
inspectable category policy over the two local models, not a classifier trained
and evaluated on the same 80 authored examples. A learned router stays deferred
until an independently labelled routing set exists.

**Built**
- `PolicyRouter` selects T0 (`qwen3:4b`) for `single_doc` and
  `guardrail_benign`, selects T1 (`qwen3:8b`) for every other known or unknown
  category, and promotes a T0 choice when retrieval confidence is below the
  configured threshold. The golden labels now describe this *initial* decision:
  24 T0 and 56 T1.
- The budget guard filters unaffordable tiers both before generation and before
  escalation. Configured local projected costs remain `$0.0`; tests inject
  non-zero costs to prove the cap and refusal paths rather than declaring a
  zero-cost branch tested by inspection.
- `answer_with_policy` implements an explicit bounded T0→T1 loop. Answerable
  abstention, structured-output failure, output-guard downgrade, or low answer
  confidence can trigger the single higher-tier retry. The final answer keeps
  the safest viable attempt, a human-readable `RoutingDecision`, and a guardrail
  event when escalation occurred.
- `make router-eval` evaluates `all_t0`, `all_t1`, `category_static`, and
  `policy_router` over the exact same cached answer receipts. It writes a
  RunManifest, per-query decision receipt, generated Markdown report, and SVG
  latency–quality chart. Failed model calls remain misses and retain their wall
  timeout latency.
- The matrix runner now checkpoints each completed golden row and resumes the
  same deterministic cell. This was added after the first 160-call attempt was
  interrupted near completion and would otherwise have discarded all partial
  work. Successful completion removes the checkpoint.

**Full-golden measurement** (Variant B, 80 rows per model)
- T0 source: strict match `40.0%`, citation-document hit `56.2%`, abstention
  accuracy `57.5%`, generation coverage `79/80`.
- T1 source: strict match `42.5%`, citation-document hit `73.8%`, abstention
  accuracy `78.8%`, generation coverage `79/80`.
- Both cells timed out on `gs_005`; the receipts preserve the `TOOL_ERR` rather
  than silently shrinking N. Local API spend is `$0.000000` (unpriced, not
  free).
- Routing accuracy is `100.0%` on all 80 labels. This is a consistency check,
  not a generalisation claim, because ADR-0004's explicit policy defines both
  the labels and the implementation.
- The dynamic policy reached `47.5%` strict match, `75.0%` citation hit, and
  `78.8%` abstention accuracy. It escalated `10/80` queries (`12.5%`), and 7/10
  escalations improved strict correctness (`70.0%` efficacy).
- In this one measured run, the dynamic policy averaged `11.0s` of gateway time
  versus `9.7s` for always-T1, a roughly 13% latency premium for a 5-point strict
  match gain. `category_static` is dominated. Phase 11 already measured about
  10% p95 latency movement between repeat runs, so close x-axis differences are
  not treated as stable rankings.

**Acceptance status**
- *Routing accuracy ≥90%:* **met in form only** at `100.0%` over 80 labels.
  Recorded this way deliberately, on review. ADR-0004 migrated `expected_tier`
  *to* the policy it evaluates, so the labels are the router serialised and the
  metric cannot fail by construction — 100% here is arithmetic, not evidence. The
  same wording was used for the Phase 9 judge labels before they were
  adjudicated, for the same reason. This AC becomes real only against a routing
  set labelled independently of the policy; until then it must not be reported as
  a passing AC in the DoD or the report.
- *Frontier over ≥4 policies generated:* **met.** The harness-generated source
  is `phase12_router_a105114011f7`; the adjacent details receipt names both
  source manifests and all per-query decisions.
- *Escalation ladder, budget guard, and `RoutingDecision` logging:* **met** in
  implementation and deterministic tests.
- *Phase-6 privacy regression remains green:* **met.** The full suite passes and
  still covers local socket blocking, no cloud-generator calls, badges, and the
  historical degraded path.
- *Phase closed 2026-08-05.* The implementation landed in `7b31c18`, the
  baseline re-pin in `8014f5d`, and the router artifact was regenerated from that
  clean SHA: `phase12_router_83f6f7c036c0` replaces
  `phase12_router_a105114011f7`, whose run_id identified no commit. Every metric
  in the regenerated run is **bit-identical** to the pre-commit run, which
  confirms the router evaluation is deterministic — it replays cached answers and
  never rerolls generation, so the same inputs produce the same frontier. The
  stale pair was removed; git history retains it.
- The two expensive source matrix receipts (`phase11_..._61802221d874`,
  `phase11_..._33c0a0d50c76`) were deliberately **not** regenerated. They cost a
  160-call run, their manifests identify the pre-phase base SHA, and the report
  names the exact source IDs it consumed. That is a disclosed tradeoff, not an
  oversight — but it does mean the frontier's source cells and its router
  manifest were produced at different commits.

**Correction to the Phase 11 entry (found on review, 2026-08-05)**
Phase 11 concluded "8B is materially more reliable and 4B is materially faster"
and treated that as the latency–quality tradeoff ADR-0003 predicted. **The
full-80 run refutes the second half.** Same metric, same units, equal call counts
(79 each):

| | 4B p50 | 8B p50 | faster |
|---|---:|---:|---|
| easy 12-row slice (Phase 11) | 3383 ms | 5604 ms | **4B, by 1.7×** |
| full 80 rows (Phase 12) | 8579 ms | 6602 ms | **8B, by 1.3×** |

The direction reverses. On the full set 8B is both more accurate (42.5% vs
40.0% strict) **and** faster, so 4B is dominated — there is no tradeoff to trade.
Phase 11's claim was an artifact of a 12-row slice of easy `single_doc`
questions, exactly the over-generalisation that entry warned against, made by
that entry. This does not change any committed number; it changes what they mean.

Consequence for ADR-0003, which replaced the cost axis with latency: a
latency–quality frontier assumes small models buy speed. On this corpus, at these
two sizes, they do not. Phase 17 must establish that the frontier has a real
tradeoff to plot before treating the chart as the headline artifact — a frontier
where one point dominates is a finding, not a chart.

**Verification so far**
- Ruff: clean.
- Deterministic suite: `98 passed` on the review environment (the implementation
  pass reported `97 passed, 1 skipped`; the optional extra is installed here).
- `pip check`: no dependency conflicts.

**Resolved 2026-08-05 — baseline re-pinned with proof.** The breakage below was
real: regenerating a retrieval manifest raised
`ValueError: baseline and Phase-4 run use different golden-set hashes`, exactly
as predicted, so the gate had been green only by comparing stale artifacts. The
hybrid retrieval eval was re-run on the current golden set
(`phase4_551b3b20b9f9`) and **all four metrics came back bit-identical to the
frozen baseline** — not within tolerance, equal to 16 decimal places:

| Metric | Baseline | Re-run | Delta |
|---|---:|---:|---:|
| `retrieval_recall@20` | 0.9785714285714285 | 0.9785714285714285 | `0.0` |
| `retrieval_precision@20` | 0.1042857142857142 | 0.1042857142857142 | `0.0` |
| `retrieval_mrr` | 0.7855867346938776 | 0.7855867346938776 | `0.0` |
| `retrieval_hit_rate` | 0.9857142857142858 | 0.9857142857142858 | `0.0` |

That is the only condition under which re-pointing a frozen reference is safe: it
proves the `expected_tier` relabel was metric-neutral for retrieval (no retrieval
metric reads that field) and, incidentally, that retrieval is deterministic
across runs weeks apart. `regression_baseline.json` now points at
`phase4_551b3b20b9f9` with hash `b59ee2659a17714c`. **Only the two identity
fields changed — every metric value and threshold is untouched**, because there
was nothing to update.

`tests/test_phase9.py` hard-pins the baseline's `source_run_id` and failed on the
re-pin. That is the tripwire working: the frozen reference cannot be re-pointed
without a test failing and a human looking. The constant was updated and the
reason recorded beside it, rather than the assertion being loosened.

Not done, and deliberately: `golden_hash` still hashes the whole golden-set file,
so any future metric-irrelevant edit will trip the guard again. Narrowing it to
metric-relevant fields would make the guard smarter and also make it capable of
missing something. That is a design change to a safety mechanism and needs its
own ADR.

Measured after the re-pin: `make verify-track-a` exit `0`, 108s wall clock, ruff
clean, `98 passed`, safety 10 rightly abstained with `injection_pass_rate 1.0`,
`judge_tpr 1.0` / `judge_tnr 1.0`, regression `passed: true` against the fresh
manifest.

**Original finding, kept for the record — the regression gate was green on stale
artifacts.** `golden_hash` is a sha256 over the raw golden-set file, and
`compare_manifest` raises on any mismatch. Changing `expected_tier` changed that
hash from `ece0ea370052e5fe` to `b59ee2659a17714c`. The new Phase 11/12 manifests
carry the new hash; `regression_baseline.json`, `phase3_baseline_latest.json`,
and `phase4_de57151e3ae3.json` still carry the old one. `make regression` passes
only because it compares two artifacts that are both stale. **The next
regenerated retrieval manifest will raise "baseline and current manifest use
different golden sets" and the gate will fail.** Retrieval metrics are unaffected
in substance — only `expected_tier` changed, and no retrieval metric reads it —
so the fix is to re-run the retrieval baseline on the current golden set and
re-pin `regression_baseline.json`, confirming the metrics did not move. That
re-pin is a deliberate act on a frozen reference and is left for an explicit
decision rather than done silently inside a router phase.
- The final SVG was rendered in its report context and inspected: title,
  zero-based axes, direct labels, non-colour marker shapes, and edge labels are
  legible with no clipping. The chart uses honest full scales, so the clustered
  points are not visually exaggerated.

**Plain-English explanation of the tricky piece.** A router is not better just
because it sends some questions to a smaller model. If that model fails and the
router retries with the larger one, the answer may improve, but the user paid
both latencies. The frontier therefore replays four policies over the same model
outputs, counts both calls on an escalation, and never rerolls generation. That
isolates the routing decision from model randomness and exposes the real result:
this router buys five strict-match points, but it does not buy speed in the
current run.

**Next:** Phase 13 — the named guardrail pipeline (Presidio tagging already
ingested → egress redaction/rehydration → numeric verifier → cross-persona check
→ advice steer → guardrail evals including over-refusal).

Carried forward, none of it resolved by closing this phase:
- Routing accuracy is **met in form only** and must not appear as a passing AC in
  Phase 16's DoD or the report until an independently labelled routing set exists.
- Phase 11's "4B is faster" claim is corrected above, and bears on ADR-0003's
  choice of latency as the frontier axis. Phase 17 must establish there is a real
  tradeoff to plot before that chart is treated as a headline artifact.
- `golden_hash` still covers the whole golden-set file; narrowing it needs an ADR.
- The internship report draft (`~/Desktop/PM-OS`) and the demo re-record
  (`demo/README.md`) remain outstanding Track-A documentation work.

---

## Phase 13 — Named guardrail pipeline  (2026-08-05)

Phase 13 is **open** with implementation and the first current-code acceptance
measurement complete. ADR-0005 chooses custom pure guards over Guardrails-AI or
NeMo and keeps the egress mechanism as an offline captured-payload contract,
because ADR-0003 retired every real cloud caller.

**Built**
- A canonical `guardrails:` config block toggles file validation, PII tagging,
  ingest and query injection checks, advice steering, egress redaction,
  citation verification, numeric verification, cross-persona isolation, and
  the output advice linter independently. The upload byte cap is configurable.
- Ingestion now validates PDF extension, size, and magic bytes; records a named
  PII-tagging event; scans document text for instruction-like content; and
  stores its `GuardrailEvent` receipts in SQLite. The Library table surfaces
  non-pass guard counts. A no-embedding rebuild processed 60/60 documents with
  zero failures.
- The input pipeline distinguishes a direct override attempt from a legitimate
  question *about* an embedded instruction. Advice-seeking queries route to a
  fixed education-not-advice response before retrieval or generation; a test
  proves both downstream call counts remain zero.
- The egress guard uses real Presidio spans, stable typed placeholders, a local
  placeholder map, and exact rehydration. It has no production caller and does
  not claim provider-wire coverage. Its contract is the exact captured payload
  the guard would emit.
- The output pipeline retains Phase 5 citation verification, recomputes cited
  invoice totals from SQLite, blocks another known persona's name or masked
  account, and replaces prescriptive model output with the fixed boundary
  response. The product Ask path now supplies these toggles and the local
  record-of-truth database.
- `make guardrails-eval` writes a RunManifest, adjacent details receipt, and
  `reports/guardrail_eval.md`. Every named guard has a positive and benign
  control. `make eval-full` now includes this deterministic Phase-13 gate.
- The Evals dashboard surfaces raw captured-egress leaks, seeded numeric
  detection, cross-persona results, and the explicit benign numerator and
  denominator.

**Measurement** (`phase13_guardrails_76c8d43a9a96`)
- Captured egress: zero raw `Marcus Chen` / `****4021` tokens; stable
  `<PERSON_1>` / `<ACCT_1>` placeholders; byte-exact rehydration.
- Numeric verification: the stored printed `$16,431.22` total for
  `PRIYA-HALCYON-004` was recomputed against the `$16,251.22` SQLite line-item
  sum, flagged, and an answer that hid the mismatch was downgraded.
- Cross-persona: all 6/6 seeded other-persona name/account leaks were blocked;
  six cached `qwen3:8b` cross-persona answers were checked, with zero leaks
  after guard application. Coverage is names and masked accounts derivable from
  SQLite; arbitrary addresses not attributable to a persona are not claimed.
- Over-refusal: **0 of 6** existing `guardrail_benign` controls were refused by
  the input or advice-output guards. Per ADR-0005, this is not reported as
  “≤5% achieved”: n=6 is underpowered and one failure would already be 16.7%.
- Injection regression: a fresh live run, `phase7_ccf079652bba`, retained
  `injection_pass_rate 1.0`, rightly abstained on 10/10 unanswerable cases, and
  answered the poisoned-document case correctly.

**Defect found by the harness**
The first egress run had zero raw PII leaks but failed exact rehydration.
Presidio included the possessive suffix in `Marcus Chen's` in one field and not
the other, producing `<PERSON_1>` and `<PERSON_2>` for the same value; rehydration
then yielded `Marcus Chen's's`. PERSON spans now leave the English possessive
outside the placeholder, so possessive and non-possessive occurrences share a
stable key. The failed provisional manifest was removed; the passing manifest
and regression test preserve the finding.

**Acceptance status**
- *Zero tagged PII in captured cloud payload:* **met as revised by ADR-0005.**
  The emitted payload has zero raw tagged values and exact rehydration. No cloud
  provider was contacted, so real wire-format integration remains unverified.
- *Numeric verifier catches seeded wrong total:* **met.**
- *Cross-persona leaks = 0:* **met on the six cached model answers and seeded
  leak controls**, limited to persona names and masked accounts available in the
  local record store.
- *Over-refusal ≤5%:* **not meaningfully tested.** Observed result is 0/6; a
  separate roughly 60-case probe set remains required for the rate claim.
- *Injection pass rate unchanged:* **met for the wrapping, narrower than it
  reads.** 1.0 on a fresh live Phase-7 run — but the safety eval calls
  `answer_question_reliable` with `guardrail_toggles=None`, and at `None` only
  `injection_scan` and `citation_verify` run. The five new guards
  (`query_injection_guard`, `advice_steer`, `numeric_verify`,
  `cross_persona_check`, `advice_linter`) were **inactive during that run**. So it
  confirms wrapping the pre-existing guards changed nothing, which is what
  ADR-0005 asked for, and does **not** show the new guards preserve injection
  resistance. Downgraded on review.
- Phase remains **open** until these changes are committed and the deterministic
  guardrail artifact is regenerated from the clean SHA.

**Review pass (2026-08-05): eval/product divergence, fixed**

The product supplied guards; no eval did. `app/streamlit_app.py` passes
`GuardrailToggles.from_config(cfg.guardrails)` and `records_db`; `evals/matrix.py`
and the safety eval passed neither. Because `reliable.py` treats `None` per-guard,
that meant **five of seven answer-path guards never ran in any measurement** — so
the benchmark measured a different system from the one that ships, and §13.4's
ablation had no "guards on" arm to compare.

Fixed: `_run_cell` now threads `guardrail_toggles`, `records_db`, and
`numeric_epsilon`; `make matrix` gains `--guardrails {off,on}`; every manifest
records `guardrails_enabled`; and the guard arm is part of the checkpoint key and
filename, so an off-arm checkpoint can never resume into an on-arm run. The
default stays `off` so no pre-Phase-13 manifest silently changes meaning — which
arm becomes canonical is a Phase 17 decision, not a side effect of a wiring fix.
`--guardrails on` fails loudly without `records.db` rather than letting
`numeric_verify` no-op into a fake "on" arm.

**Ablation — the guards are close to free** (full 80 rows, both arms, same
golden set; off-arm cells are the committed `61802221d874` / `33c0a0d50c76`,
on-arm are `35d35e2fb62f` / `eea876388398`, report
`reports/model_matrix_guards_on.md`)

| | 4B off → on | 8B off → on |
|---|---|---|
| strict match | `0.4000 → 0.4000` (0) | `0.4250 → 0.4250` (0) |
| citation hit | `0.5625 → 0.5625` (0) | `0.7375 → 0.7250` (−1 row) |
| abstention accuracy | `0.5750 → 0.5750` (0) | `0.7875 → 0.7750` (−1 row) |

The full guard stack costs **one row out of eighty on 8B and nothing on 4B**.
Failure sets are identical between arms. That is the price of `numeric_verify`,
`cross_persona_check`, `advice_linter`, `advice_steer`, and
`query_injection_guard` stated in measured terms, and it is the strongest
argument for leaving them on.

**Latency is environment-dominated and cannot currently rank models — and this
corrects the correction in the Phase 12 entry.**

The two arms produced *identical answers* — same metrics, same failure sets — yet:

| | off arm | on arm | change |
|---|---:|---:|---|
| 4B p50 | 8579 ms | **3714 ms** | −57% |
| 4B p95 | 17900 ms | 9592 ms | −46% |
| 8B p50 | 6602 ms | 6908 ms | +5% |

Guards add work, so they cannot make a model 57% faster. The 4B off-arm run also
carried a generation timeout (coverage `0.9875` vs `1.0000` on-arm) that did not
recur. Both point at machine load during that earlier run, not model behaviour.

The consequence is that the Phase 12 entry's "correction" — that Phase 11's "4B is
faster" was refuted because 4B p50 `8579` exceeded 8B's `6602` — **rested on a
single unreliable measurement, and this run reverses it again** (4B `3714` vs 8B
`6908`, 4B faster by 1.9×). That correction was written by the reviewer, in the
same over-generalising move it accused Phase 11 of. Neither run establishes a
ranking. The honest statement is: **this harness cannot currently rank these
models by latency at all.**

Phase 11 measured ~10% p95 movement between repeat runs and called it noise; this
is ~50% p50 movement on identical outputs. That escalates the ADR-0003 problem
rather than restating it: latency is the frontier's x-axis, and a
latency–quality frontier built from single runs is not measurable. Before Phase 17
treats that chart as a headline artifact it needs repeated cells, a reported
spread, and controlled machine conditions — or a different x-axis.

**Verification so far**
- Full acceptance run: Ruff clean and `109 passed`; after adding the final
  output-pipeline/UI regression controls, the deterministic suite is
  `110 passed, 1 skipped` in the sandboxed environment.
- Focused Phase 5/6/7/13 guard tests passed.
- Derived corpus rebuild: 60 documents, 0 failures, 60 chunks.
- Live safety regression: 11/11 programmatic outcomes correct; judge TPR/TNR
  `1.0 / 1.0`; retrieval regression green with zero metric deltas.

**Plain-English explanation of the tricky piece.** A guard can fail in two
directions: miss something dangerous or block something legitimate. The
harness therefore pairs a bad fixture with a benign control for every named
guard and keeps the numerator visible. The egress failure is why this matters:
“zero leaked names” looked green, but exact round-trip checking caught that the
safe-looking placeholders would have mangled the answer shown to the user.

**Next:** commit Phase 13, regenerate `make guardrails-eval` from the clean SHA,
then begin Phase 14's bounded agentic-RAG variant. The separate ~60-case benign
probe remains a measurement debt, not a silently passing AC.
