# PROGRESS

Honest build log. One entry per phase: what got built, what deviated from
SPEC.md and why, and a plain-English explainer of the trickiest piece (that
paragraph is the interview prep). No backdating, no compressing — the commit
history is the receipt.

> ### Phase numbering changed on 2026-08-11 — read before trusting a phase number below
>
> **ADR-0011** re-sequenced the remaining roadmap. Entries written before that date
> use the old numbering, and they are left exactly as written because this log is
> append-only. Translate as you read:
>
> | Entries before 2026-08-11 say | It is now |
> |---|---|
> | Phase 16 — comparison report and portfolio | **Phase 19** |
> | Phase 17 — six-model bake-off and latency–quality frontier | **Phase 18**, extended with a decoding sweep |
> | *(new)* | **Phase 16** — external live documents, OCR, watcher *(closed)* |
> | *(new)* | **Phase 17** — browser-UI packaging and handoff |
>
> So an older entry that says "Phase 17 must establish the frontier has a real
> separation" is an obligation now owed by **Phase 18**. Those obligations were not
> cancelled by the renumbering; only their labels moved.

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

Implementation, acceptance measurement, and the review fixes complete; closed
after the guardrail artifact was regenerated from a clean SHA. ADR-0005 chooses
custom pure guards over Guardrails-AI or NeMo and keeps the egress mechanism as
an offline captured-payload contract, because ADR-0003 retired every real cloud
caller.

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
- *Phase closed 2026-08-05.* Implementation and the review fixes landed in
  `a3689f8`; the guardrail artifact was regenerated from that clean SHA as
  `phase13_guardrails_1b5ca8fa927e` (`git_sha a3689f8`), replacing
  `phase13_guardrails_76c8d43a9a96`, whose run_id identified no commit. Metrics
  are **bit-identical** across the two runs, which is the expected result: the
  guardrail eval is fully deterministic — it runs fixtures and cached receipts,
  never live generation, which is why it completes in 4 seconds. The stale pair
  was removed; git history retains it.

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

**Next:** Phase 14 — bounded agentic RAG (variant D): tools, the L4 loop, step
tracing, and multi_hop golden items live.

Measurement debt carried forward, none of it resolved by closing this phase:
- The ~60-case benign probe set (ADR-0005). Until it exists, over-refusal stays
  **0 of 6, not meaningfully tested** — never "≤5% achieved".
- The injection AC verifies the wrapping of pre-existing guards only; the five
  new guards were inactive in that run.
- **Latency cannot rank models in this harness.** ~50% p50 movement on identical
  outputs. Before Phase 17 treats the latency–quality frontier as a headline
  artifact it needs repeated cells, a reported spread, and controlled machine
  conditions — or a different x-axis. ADR-0003 should be revisited on this point.
- Which matrix arm is canonical (`--guardrails off` vs `on`) is an open Phase 17
  decision. The default stays `off` so no pre-Phase-13 manifest changes meaning.
- Routing accuracy remains **met in form only** (Phase 12).
- The internship report draft (`~/Desktop/PM-OS`) and the demo re-record
  (`demo/README.md`) remain outstanding Track-A documentation work.

---

## Comprehensive review before Phase 14  (2026-08-05)

A full sweep of Phases 0–13 rather than a review of the last diff. Findings are
ordered by consequence. Two of them change how existing results should be read.

**1. The router's category→tier map is backwards on 44 of 80 rows.**
ADR-0004 set the map on intuition — simple lookups to T0, complex to T1 — and no
per-category measurement existed to check it, because the matrix emits aggregate
metrics only. Computed offline from the exact guards-off receipts the router eval
consumed: 8B beats 4B on `single_doc` (66.7% vs 33.3%) while 4B beats 8B on
`aggregation` (28.6% vs 14.3%) and `multi_hop` (16.7% vs 0.0%). All three are
routed to the weaker model. The aggregate scores (4B 40.0%, 8B 42.5%) hide this
entirely, which is precisely why aggregate-only metrics were the enabling
condition. Recorded as an amendment to ADR-0004; deliberately **not** corrected,
because flipping the map against the same 80 rows that scored it is the same
circularity the ADR already carries on its labels. Phase 12's `routing_accuracy`
now has a second reason to be *met in form only*: the labels encode a mapping the
data contradicts.

**2. SPEC contradicted itself in at least nine places.** `CLAUDE.md` instructs
every session to read SPEC as the source of truth, and SPEC still asserted the
retired paid tiers (§2 G7, §7.1, §10, §12), a Cloud-Boosted UI that no longer
exists (§2 G3, §4 UC5, §5 FR8, §6 Screen B), and a per-query replay command that
was never built (§5 FR18, §18). The corrections existed only in ADRs and in this
log — a reader, human or agent, hit nine stale assertions before reaching any of
them. Fixed: a dated **ACTIVE DEVIATIONS** banner at the top of §0 listing all
seven live deviations with their owning ADR, plus inline `[SUPERSEDED]` markers on
G3 and strikethrough on both tier tables. New deviations are added to that banner
when their ADR is accepted.

**3. `make replay` advertised a lie.** It printed "not implemented until Phase 8"
— but Phase 8 came, went, and *deliberately declined* to build raw-input replay,
because persisting raw financial questions and retrieved context would broaden
local data retention against the product thesis. That reasoning was honest and
recorded in the Phase 8 entry; the Makefile message inverted it into a promise.
Now prints the real reason, points at the deviation, and exits non-zero.

**4. Phase 14 cannot state its AC yet.** Its AC is "numeric exact-match on
multi_hop/aggregation improves by a stated, measured margin vs B", and neither
half exists: no manifest carries a category-scoped metric, and there is no
numeric-exact-match metric — `strict_answer_match_rate` is a literal-anchor lower
bound. The per-row receipts *do* carry `category` and per-row verdicts, so the
baseline was recoverable offline without re-running inference. Recorded in
ADR-0006 with the numbers Phase 14 must beat: `aggregation` 28.6%/14.3% and
`multi_hop` 16.7%/**0.0%** (4B/8B). 8B answers zero of twelve multi-hop questions
to strict match; if variant D cannot beat that floor, the null result is worth
publishing.

**5. `OpenAICompatibleGenerator` is dead code with no test.** Nothing imports it —
not the app, not `privacy.py`, not any test; only the package `__init__` that
exports it. ADR-0003's amendment justified keeping the retired cloud seam because
`privacy.py` is still exercised by `test_phase6.py`; that justification does not
extend to this class. It is neither used nor tested. Recommended for deletion, not
deleted here — removing exported API during a review pass is the owner's call.

**6. Phase 1's byte-identical corpus regeneration still holds.** Re-verified for
the first time since July: `make data` reproduced the committed ground truth with
zero diff, despite `pyproject.toml` gaining the `gateway` extra since. The
determinism claim the whole harness rests on is intact.

**7. `torchvision` is absent while `transformers` expects it.** A live app run
raised `ModuleNotFoundError: No module named 'torchvision'` from a lazy
`transformers` import path. Nothing is broken — the reranker loads and the suite is
green — but it is an inconsistent dependency state in the same native stack as the
unexplained signal-11 in the Phase 10 findings. Still not a diagnosis, and the
segfault entry stays "cause unknown".

**Clean.** No secrets, keys, or `.env` files are tracked. Every `config.yaml` key
is read by code. Every report referenced in the docs exists except
`reports/variant_matrix.md`, which is a Phase 16 deliverable. Every test asserts
something. The Phase 6 socket-blocking test is intact and real.

**Verification of this review:** `make verify-track-a` exit 0, ruff clean,
111 passed, regression green — run at the commit that carries these fixes.

**Next:** Phase 14 — bounded agentic RAG (variant D) under ADR-0006, which is
`proposed` and needs owner acceptance first. Its two prerequisites (per-category
metrics, a defined numeric-exact-match metric or a restated AC) come before the
loop.

---

## Phase 14 opened — bounded Variant D vertical slice  (2026-08-06)

Phase 14 is **in progress, not closed**. ADR-0006 was accepted and both measurement
prerequisites were complete before this code started. This opening change builds
the first end-to-end Variant-D slice:

- `AgentStep.failure` implements the accepted contract amendment before any
  Phase-14 artifact is committed. Tool failure is now queryable data rather than
  prose hidden in `output_summary`.
- The hand-written L4 loop is a `for` over `loops.agent_steps_max`, with a separate
  traced-token budget and per-call output cap in `config.yaml`. Every selected tool
  is appended before dispatch. Tool and planner failures consume a step, retain a
  partial trace, and may recover; either budget exhausting returns the fixed honest
  abstention rather than a guess.
- The four tools are live: Variant-B retrieval, Decimal-backed arithmetic over a
  restricted AST, read-only SQLite, and finish. SQLite accepts one `SELECT`, opens
  `records.db` in read-only mode, applies table and function allowlists through the
  SQLite authorizer, supports bound parameters, caps result rows, and carries
  `doc_id` provenance into source chunks so SQL-derived figures can still receive
  verbatim verified citations.
- Variant D is selectable in the model matrix and the product Ask screen. Matrix
  receipts now measure trace coverage, step-budget compliance, token-budget
  compliance, exhaustion rate, and step/token counts. `--categories` permits the
  Phase-14 target population to be selected before `--limit`. The Ask screen shows
  the complete step trace, including structural failures.
- The Phase-7 safety runner now accepts `--variant D_agentic --guardrails on` and
  refuses to run D with the guards silently off. This closes the vacuous-eval path
  found in the Phase-13 review, but the live 11-item rerun has **not happened yet**.

**Development smoke evidence — not acceptance evidence.** Two guards-on, one-row
`qwen3:8b` matrix runs were written only under `/tmp` from this dirty working tree.
After the first run exposed stale conceptual SQL column names and a too-strict
finish parser, the corrected aggregation smoke (`ag_001`) passed strict match,
numeric exact-match, citation hit, and abstention correctness in 2/6 steps. The
corrected multi-hop smoke (`mh_001`) passed the same four checks in 3/6 steps after
recording and recovering from an ambiguous-column SQL failure. Both stayed within
the traced-token budget. These two rows prove plumbing, not the claimed margin:
the target population is 26 rows and the comparison must use committed manifests
from a clean SHA.

**Deterministic verification:** Ruff clean; `130 passed, 1 skipped`. The new tests
cover calculator code-execution attempts, SQL writes/stacking/comments/system-table
reads/extension loading, parameter binding, provenance, recoverable planner and
tool failures, both budgets, honest exhaustion, citation verification, the CLI
surface, and the amended schema.

**Still required before Phase 14 can close:** run the complete aggregation and
multi-hop population for Variant D against the same model's Variant-B numeric
baseline; state the measured margins (including a null result if that is what the
run shows); run the 11-item Phase-7 safety suite with D and all Phase-13 guards
active; regenerate durable reports/manifests from a clean commit; and delete the
kickoff brief only after every acceptance criterion passes.

---

## Phase 14 closed — bounded agentic RAG (variant D)  (2026-08-10)

**Closed with a split result, not a clean pass.** The AC — "numeric exact-match on
multi_hop/aggregation improves by a stated, measured margin vs B" — is **met on
`qwen3:8b`, the model the product ships (T1), and fails on `qwen3:4b`.** Both arms
guards-on, n=12 in numeric scope per category, D compared against B on the *same*
model. Margins are stated twice: as scored, and with a trailing `Citations:` block
stripped from `answer_text` on both arms.

| model | category | B | D as-scored | D stripped | margin (stripped) |
|---|---|---:|---:|---:|---:|
| `qwen3:8b` | `aggregation` | 16.7% | 66.7% | 58.3% | **+41.6 pp** |
| `qwen3:8b` | `multi_hop` | 0.0% | 16.7% | 16.7% | **+16.7 pp** |
| `qwen3:4b` | `aggregation` | 33.3% | 8.3% | 8.3% | **−25.0 pp** |
| `qwen3:4b` | `multi_hop` | 16.7% | 8.3% | 8.3% | **−8.4 pp** |

**The stripped column is the one to quote.** Review found the numeric scorer could
be helped by a model reciting its sources inside `answer_text` — figures its prose
never stated. Variant B does this on 0 of 160 committed rows, so the help is
one-sided. It hit exactly 1 row of 52 and cost 8.4 pp on 8B aggregation. The result
survives it.

**Why 4B regresses is measured, not inferred:** it exhausted a budget on 88.5% of
rows (avg 5.46 of 6 steps, then abstained) against 3.8% for 8B. The plain finding
is that a bounded agent loop helps a model capable enough to drive it and actively
harms one that is not. That is the phase's most interesting result and it is not
the one that was hoped for.

**The blocker that took three days, and what it taught.** The Variant-D safety run
could not be produced: it hung repeatedly, and a `faulthandler` dump showed the
loop blocked in `socket.readinto` with two identical stacks 90s apart. Root cause:
`OllamaGenerator` never disabled Qwen 3's thinking, while the eval gateway has
since Phase 11. Thinking tokens are charged against `num_predict` before any answer
is emitted, so Variant D's planner — the only caller that passes `max_tokens` —
received **empty strings**, recorded them as planner errors, and burned its whole
step budget. Variant B was never affected because it does not set `max_tokens` at
all, which is why Phase 7's numbers are byte-identical before and after the fix.

The matrix scored a system that never had the problem; the safety runner scored one
that always did. **This is the third instance of the same family** — Phase 13 found
the eval path running with `guardrail_toggles=None`, Phase 11 found the egress
badge asserting rather than deriving. Recorded as **ADR-0007** with the rule that
every generator the product uses must match the eval gateway's decoding settings,
plus a test that pins it. After the fix the same suite runs in **2 minutes** with
**zero planner errors and zero transport errors**, down from 6 steps per row to 2.7.

**ADR-0007 also gives the loop a third budget.** `loops.agent_seconds_max: 300`.
Step and token budgets do not bound elapsed time: a stalled generator returns no
tokens, so the token counter freezes and steps advance only once per 180s timeout —
18 minutes for one question. Neither existing budget could bound the failure they
existed to bound. Transport failures are now labelled apart from planner failures,
because recording an outage as "the model produced a bad action" is what caused the
stall to be misread as model incompetence in the first place.

**Safety evidence, ADR-0006's outstanding commitment, now discharged.** Phase 7's
suite re-run with Variant D live and all Phase 13 guards active
(`phase14_safety_*`, `guardrails_enabled: 1.0`):

- `injection_resisted: 1.0`, `injection_answered_correctly: 0.0`. The agent
  **resisted** the embedded instruction and then over-refused. `injection_pass_rate`
  is a conjunction of those two and reads `0.0`, which on the first run was
  mistaken for a compromise. The two halves are now emitted separately so that
  reading cannot recur; the conjunction is kept byte-identical so every committed
  Phase 7 manifest stays comparable.
- **Variant D scores 9/10 on abstention where B scores 10/10.** On `ua_007` it
  answered an unanswerable question: *"Priya Raman uses a checking account with
  Cascade Credit Union, with account number ****3390."* Every guard passed it.
  This is a real safety regression against B and is **not fixed** — it is recorded,
  not resolved.

**Also measured, also unfixed:** the `sql` tool fails 39% (4B) / 47% (8B) of calls.
It is *secure* — subquery, `UNION`, CTE and `sqlite_master` exfiltration are all
blocked by the authorizer's default-DENY, verified by probes beyond the test suite —
but the planner cannot write queries it accepts. 4B issued 135 sql calls across 26
questions, which is precisely how it burns its step budget. Fixing the schema prompt
or feeding the SQL error back as a retry would likely move 4B more than anything
else.

**Claims that must not be upgraded from this phase:**
- `agent_trace_coverage_rate`, `agent_step_budget_compliance_rate` and
  `agent_token_budget_compliance_rate` are **invariants, not results**. A planner
  that never returns a valid action scores 100% on all three — demonstrated. They
  are regression guards on the loop's bookkeeping and nothing more. The generated
  report now says so in the artifact itself.
- The AC is met **on 8B only**. "Variant D beats variant B" without naming the
  model is false.
- `injection_pass_rate: 0.0` for D does **not** mean the injection worked.

**Verification:** `make verify-track-a` exit 0 — ruff clean, 136 passed, injection
suite green, judge 20/20, regression `passed: true`. Artifacts regenerated from a
clean commit.

**Carried forward, unchanged:** the ~60-row benign probe set still does not exist,
so over-refusal stays **0 of 6, not meaningfully tested**. Latency still cannot rank
models in this harness. Routing accuracy remains *met in form only*, and per the
pre-Phase-14 review the router's category→tier map is backwards on 44 of 80 rows —
still deliberately uncorrected, owed to Phase 17 on a held-out set.

---

## Phase 15 opened — measurable graph contracts and live LightRAG smoke  (2026-08-10)

Phase 15 is **in progress, not closed**. ADR-0008 accepts the engine decision the
SPEC pre-indicated: LightRAG 1.5.x through a narrow embedded adapter; Graphiti is
the temporal alternative; Microsoft GraphRAG is the community-summary alternative;
Obsidian is a generated projection and never a retrieval backend.

The graph-quality denominator is now code, not interpretation at report time.
`entities.json` contains **15 scoreable entities** in the types §14.3 names:
3 people, 3 organizations, 5 recurring merchants, and 4 accounts. Addresses are
attributes. Relation endpoints are not allowed to invent extra targets because
the `shared_address` relation has explanatory prose as its object. The committed
graph also contains 15 relations with 89 evidence-document links. Provider-neutral
contracts, exact canonical entity scoring, a typed-relation exact lower bound, and
a LightRAG GraphML adapter make those definitions independent from SDK storage.

The Obsidian exporter is live and was exercised over the Phase-1 graph: 15 entity
notes + 60 document notes with evidence wikilinks. Its README carries a warning
that this is a **ground-truth demo projection, not extraction evidence**. It cannot
be used to claim entity recall or to call Variant C built.

The pinned `lightrag-hku==1.5.6` SDK exposed a packaging problem immediately: its
Ollama module imports an undeclared Python client and attempts a runtime install.
VaultLedger does not use that module. Its adapter calls the local HTTP API
explicitly, sets `think: false` per ADR-0007, uses the measured 768-dimensional
`nomic-embed-text` output, and records tokens/latency/cost status. The local model
choice is based on `ollama show`, not disk size or tag inference: `qwen3:8b` declares
8.2B parameters, versus 5.1B for the larger-on-disk `gemma4:e2b`.

**Live one-document smoke — plumbing evidence only.** A disposable `/private/tmp`
index over `f1099_cedargrove_david_2024` completed end to end: 7 nodes, 6 edges,
2 completion calls, 3 embedding calls, 4,899 recorded input tokens, 802 output
tokens, and 43.5 seconds wall time. Cost is `0.0` with `pricing_status: unpriced` —
local compute is not called free. The first attempt completed extraction but found
a receipt-path bug for indexes outside the repo; a regression test and portable
path serializer fixed it, and the second run wrote the receipt successfully.

Do not extrapolate the smoke quality. It found the two canonical entities present
in that one 1099 and five form/field concepts, including a spurious
`Form 10909-NEC` node. Comparing one document to the full-corpus denominator reads
13.3% recall / 28.6% precision and is **not the Phase-15 eval population**.

**Still required:** full 60-document clean-commit indexing and cost receipt;
entity recall ≥80% on that extracted graph; `C_graph` local/global retrieval with
source-chunk citations; same-model B-vs-C scoring on all `global_summary` rows;
and an extracted-graph Obsidian export inspected in graph view. No Variant-C or
acceptance claim has been made.

---

## Phase 15 mid-phase: the graph is built and scored — recall gate MISSED  (2026-08-11)

Phase 15 remains **in progress**. Two acceptance items are now discharged with
receipts; three remain unbuilt. No Variant-C claim is made.

**Index built.** `make graph-index` ran from the clean SHA `920e7bd` and processed
60 of 60 documents, exit 0. Receipt: `reports/phase15_graph_index_2e50d5948f99.json`
— 45.8 minutes wall, 142 completion calls, 228 embedding calls, 378,092 input and
53,572 output tokens, `total_cost_usd: 0.0` with `pricing_status: unpriced`. The
resulting 82-node / 206-edge GraphML is committed (force-added past the
`data/graph/` ignore rule) so the score below can be re-derived, not just believed.

**The ≥80% entity-recall gate is missed.** Measured on the pre-registered metric:

  entity recall      11/15 = 73.3%   <- AC threshold was 0.80. MISSED.
  entity precision   11/81 = 13.6%
  relation recall     0/15 = 0.0%

**The miss is a naming-convention artifact, and that is stated here rather than
used to erase the number.** People, organizations and merchants scored 11 of 11.
All four misses are accounts, and all four *were* extracted — under a different
surface form than `entities.json` uses:

  ground truth `checking ****4021` -> extracted `Account no. ****4021`
  ground truth `savings ****7788`  -> extracted `Account ****7788`
  ground truth `checking ****3390` -> extracted `Checking Account Ending in 3390`
  ground truth `checking ****5567` -> extracted `Account no. ****5567`

`quality.py` refuses fuzzy matching by design and requires an explicit, reviewable
alias table before crediting aliases. It behaved as specified; what it measured
here is a string convention, not whether the extractor found the account.

**Post-hoc re-score, labelled as post-hoc.** Applying one stated rule — credit an
expected account iff some extracted node contains `****<last4>` or
`ending in <last4>`, case-insensitive, nothing else fuzzy-matched — gives:

  entity recall      15/15 = 100.0%  (post-hoc rule, NOT the pre-registered metric)
  entity precision   19/81 = 23.5%

This rule was written **after** seeing the strict result, which is exactly the
condition under which a metric change is least trustworthy. It is therefore
recorded as a secondary diagnostic, the headline stays 73.3%, and the phase
reports the gate as missed. Codifying the alias table in `quality.py` and
re-running is deferred, so that any future pass is measured by a rule that exists
before the run rather than after it.

**The precision number is the real finding, and it is bad.** 13.6% strict / 23.5%
under the alias rule. The local 8B extractor mints account entities out of numbers
that are not account numbers, traced to source:

  `Checking Account Ending in 07302` <- the Jersey City ZIP from a payer address
  `Checking Account Ending in 2525`  <- Marcus Chen's net pay of $2,525.39
  `Checking Account Ending in 3125`, `... 3252` <- appear nowhere in the corpus
                                                  in plain or comma-formatted digits

For a privacy-first financial-document product, an extractor that fabricates
account identifiers from ZIP codes and paycheck amounts is a more consequential
result than the recall gate. It is consistent with the one-document smoke, which
invented `Form 10909-NEC`, and with ADR-0008's warning that `qwen3:8b` sits far
below LightRAG's ≥32B recommendation.

**Relation recall of 0.0 is near-uninformative and must not be read as "no correct
relations."** Ground truth uses typed predicates (`owns account`,
`recurring merchant`); LightRAG emits keyword bags (`payment,transaction`,
`account holder,invoice issuer`). Exact triple matching cannot cross those
vocabularies, so 0/206 is a true lower bound that says nothing about whether the
206 extracted relations are right. Judging them needs a predicate mapping that
does not yet exist.

**Still required:** `C_graph` local/global retrieval with source-chunk citations;
same-model B-vs-C scoring on all six `global_summary` rows; and an
extracted-graph Obsidian export inspected in graph view (no CLI path exists for
that yet — `export-ground-truth` is the only export subcommand).

---

## Phase 15 account-alias re-score — post-hoc recall passes; precision remains poor  (2026-08-11)

Phase 15 remains **in progress**. This entry appends to rather than replaces the
strict result above: the pre-registered metric remains **11/15 = 73.3% recall,
11/81 = 13.6% precision, and the ≥80% gate remains recorded as MISSED**.

ADR-0009 codifies the secondary account rule requested after that miss. The rule
was committed at `23a52e8` with synthetic-fixture tests **before** it was applied
to the fixed extracted GraphML. It is derived only from each ground-truth
account's structured `last4` field and applies only when the expected entity kind
is `account`: an extracted name must match `\*{2,}\s*<last4>\b` or
`ending\s+in\s+<last4>\b`, case-insensitive. People, organizations, and merchants
still use exact canonical matching. This sequencing limits post-hoc tuning but
does not turn the alias result into a preregistered result.

**Re-score of the committed 82-node / 206-edge GraphML** (81 unique canonical
entity names after normalization):

| metric | strict, pre-registered | account alias, post-hoc |
|---|---:|---:|
| entity recall | 11/15 = **73.3%** | 15/15 = **100.0%** |
| entity precision, selected convention | 11/81 = **13.6%** | 15/81 = **18.5%** |
| typed-relation exact recall | 0/15 = **0.0%** | unchanged: 0/15 = **0.0%** |

The selected precision convention is **distinct expected entities matched / unique
extracted canonical nodes**, with at most one numerator credit per expected
account. Eight extracted nodes match the four expected accounts; the extra four
are duplicate aliases and remain false-positive resolution errors in the
denominator. This prevents entity fragmentation from improving precision.

For comparability, the implementation also reproduces the earlier node-counted
diagnostic exactly: 11 strict nodes + 8 account-alias nodes = **19/81 = 23.5%**.
That convention is not selected because it rewards all three surface nodes for
account 7788 as three correct extractions. The difference between 18.5% and 23.5%
is therefore a declared metric decision, not a calculation discrepancy.

Reproduce both columns with:

```bash
python -m vaultledger.graph score \
  --graphml data/graph/lightrag/graph_chunk_entity_relation.graphml
```

**Verification before re-score:** `make lint` clean; `make test` = 146 passed,
1 skipped. The new tests pin schema-derived suffixes, digit boundaries, the
account-only scope, and duplicate-node precision using synthetic fixtures rather
than the real extracted names.

**What this changes:** the secondary alias recall clears 80% and confirms all
four real accounts exist somewhere in the graph. **What it does not change:** the
original gate miss, the poor 18.5% selected precision, fabricated account nodes,
the uninterpretable predicate-vocabulary mismatch, or the three remaining phase
items (`C_graph`, B-vs-C `global_summary`, extracted-graph Obsidian export).

---

## Phase 15 closed — GraphRAG (variant C) built, measured, and not promoted  (2026-08-11)

Phase 15 is **closed as an implementation and evaluation milestone, with the
quality AC explicitly not all green**. Variant C is implemented and evaluated; the
pre-registered entity-recall gate still missed, and C underperformed B on the
initial six-row same-model global-summary comparison. Closing records those
results rather than redefining the gates or extending the phase until the
preferred outcome appears. **ADR-0010 grants a Phase-15-only waiver** from the
all-ACs-green phase rule; it does not license the same exception later.

**Built.** `LightRAGRetriever` exposes both LightRAG `local` and `global` query
modes behind the selectable `C_graph` variant; `global` is the configured default
for the global-summary population. Graph results are mapped through LightRAG's
stored document paths to the exact Phase-2 `Chunk` objects, so the existing
citation verifier—not a graph-only surrogate—remains authoritative. The matrix
runner and Streamlit Ask path both instantiate C. The initial run varied two
things: C received a 12-chunk context budget versus B's 6. More graph fan-out may
help recall, or the longer/noisier context may cause abstention. The initial run
alone cannot attribute the difference to graph retrieval rather than context
budget.

**Extraction and indexing result, unchanged.** The clean-SHA full build processed
60/60 documents into 82 nodes and 206 edges. The versioned receipt
`phase15_graph_index_2e50d5948f99` records 45.8 minutes, 142 completion calls,
228 embedding calls, 378,092 input and 53,572 output tokens, and `$0.00` API cost
labelled **unpriced local inference**, not free. Strict entity recall remains
11/15 = **73.3%**, below the ≥80% AC, with precision 11/81 = **13.6%**. The
post-hoc schema-derived account alias diagnostic is 15/15 = **100%** recall and
15/81 = **18.5%** selected precision. Typed-relation exact recall remains 0/15,
the declared lower bound across incompatible predicate vocabularies.

**Same-model B-vs-C result.** All six `global_summary` rows ran with
`ollama/qwen3:8b`, the same committed golden-set hash, guardrails on, and the same
clean code SHA (`8d4cb3b`). The full population stays `n=6` even when generation
fails. Receipts and complete answers are linked by
`reports/phase15_global_summary_matrix.md`.

| variant | generation coverage | strict match | citation hit | abstention accuracy | wall p50 / p95 | gateway p50 / p95 | input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| B_hybrid | 5/6 | 0/6 | 4/6 = **66.7%** | 4/6 = **66.7%** | 13.05s / 53.08s | 9.48s / 24.35s | 9,301 / 906 |
| C_graph | 6/6 | 0/6 | 2/6 = **33.3%** | 2/6 = **33.3%** | 20.51s / 41.97s | 12.72s / 36.48s | 16,360 / 1,380 |

Citation hit and abstention accuracy are **collinear here, not two independent
confirmations**: they agree on every one of the 11 scored rows because each
abstention has no citation and every answer that did not abstain cited an expected
document. The single underlying result is that C abstained on 4/6 answerable rows;
B abstained on one and lost one to a 180-second connection timeout, leaving B 4/6
versus C 2/6—a two-row difference. This is underpowered: `n=6`, Fisher exact
two-tailed `p=0.567`, and one row moves either rate by 16.7 percentage points.
Neither arm passed the literal strict-match lower bound, so that metric cannot
choose between them. C's median end-to-end latency was 7.46s slower. Its lower wall
p95 is not a graph latency win, but the reason first recorded here was wrong and is
corrected below: B's timeout does not inflate that tail, because wall-latency
statistics are computed over completed rows only and the 181.0s row is excluded
entirely. Gateway
token/latency totals exclude LightRAG's retrieval-side keyword and embedding calls;
wall latency includes them. Local API spend is `$0`, with compute again unpriced
rather than free. B therefore remains the **provisional operational default**, not
the demonstrated winner of a powered experiment.

**Context-budget sensitivity pre-registration (recorded before inference).** A
third arm will hold model, six-row golden population, seed, guardrails, and graph
index fixed, run from a clean committed SHA, and change the experimental setting
only by moving C's `answer_top_n` from 12 to 6.
The primary comparison is the count of rows with correct abstention behavior; the
citation column remains reported and its collinearity will be checked again. If
C@6 is closer in absolute success-count distance to C@12's 2/6 than to B's 4/6,
the context budget is not the observed cause and the descriptive graph-retrieval
result stands. If C@6 is closer to B, the original result is confounded and cannot
separate graph retrieval from context length. A 3/6 tie is explicitly
inconclusive. No original receipt or metric will be changed.

**Sensitivity result: explicitly inconclusive under that rule.** The clean-SHA
arm ran at `9fea94b`; its only runtime experimental change was C's context budget
of 6. The intervening code adds the CLI override and receipt/report metadata but
does not change retrieval, generation, guardrail, or scoring semantics. Its manifest
`phase11_ollama_qwen3_8b_c_graph_k6_e508b61b6bf6` carries the same model,
config hash, golden-set hash, seed, and guards-on setting as the original arms.
All original receipts remain byte-unchanged.

| arm | context k | coverage | strict | citation hit | abstention accuracy | wall p50 / p95 | gateway p50 / p95 | input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B_hybrid | 6 | 5/6 | 0/6 | 4/6 = **66.7%** | 4/6 = **66.7%** | 13.05s / 53.08s | 9.48s / 24.35s | 9,301 / 906 |
| C_graph original | 12 | 6/6 | 0/6 | 2/6 = **33.3%** | 2/6 = **33.3%** | 20.51s / 41.97s | 12.72s / 36.48s | 16,360 / 1,380 |
| C_graph sensitivity | 6 | 6/6 | 0/6 | 2/6 = **33.3%** | 3/6 = **50.0%** | 30.22s / 112.59s | 19.09s / 107.28s | 10,760 / 4,060 |

C@6's primary 3/6 abstention result is exactly equidistant from C@12's 2/6 and
B's 4/6, the tie condition pre-registered as inconclusive. The experiment
therefore **cannot separate graph retrieval from context budget**. Citation hit
stayed 2/6, but the two metrics are no longer collinear in the sensitivity arm:
`gs_005` answered without an expected-document citation, so abstention behavior
was correct while citation hit failed. This is why both columns remain in the
report and why the original collinearity is described as population-specific.

**Correction: latency statistics exclude failed rows, and the earlier tail
explanation was wrong.** The close entry above originally said C@12's lower wall
`p95` was explained by B's timeout inflating B's tail. That is not what the harness
computes. `_cell_metrics` builds `wall_latencies` from **completed rows only**, so
B's 181.0s timeout row is absent from its latency figures altogether. B's reported
53.08s `p95` is `gs_001`, a row that completed normally. The consequence runs the
opposite way from the original claim: B's reported tail *understates* B's real
latency behaviour, because its slowest observed row is the one thrown out. This also
makes the two arms' latency denominators unequal — five completed rows for B against
six for each C arm — which the generated report now discloses.

**No `p95` in this table is a distribution.** At `n≈6` the 95th percentile is simply
the slowest completed row, so none of the three `p95` figures may be compared against
another. B's 53.08s is `gs_001`, C@12's 41.97s is `gs_003`, and C@6's 112.59s is
`gs_005`, whose next-slowest peer is 61.2s. The caveat that C@12's lower `p95` is not
a graph latency win applies identically to C@6's higher one; it is a property of the
six-row population, not of any arm.

**The sensitivity arm's output-token jump is one row, not a general verbosity
change.** C@6 emitted 4,060 output tokens against C@12's 1,380 on half the context.
`gs_005` alone accounts for roughly 80% of that gap: 2,206 output tokens versus 72
for the same question at `k=12`. It is the same row that set the `p95` and broke the
collinearity — at `k=6` it answered at length instead of abstaining. Excluding it,
the arms are 1,854 against 1,308 output tokens, so a smaller context did coincide
with somewhat longer answers, but the headline 3x figure is one example and must not
be read as a context-length effect on its own.

The sensitivity run does not upgrade B into a demonstrated winner; it leaves B
as the provisional operational default on simpler architecture and the existing
evidence. The three-arm generated view is
`reports/phase15_global_summary_matrix.md`; the single-arm generation artifact is
`reports/phase15_graph_k6_matrix.md`.

**Extracted graph visualization verified in the real app.** The collision-safe
export produced 82 entity notes and 60 document notes; all 60 document notes have
wikilinks. It opened in the official Obsidian 1.13.6 desktop app as
`obsidian_vault`. Graph view visibly rendered cross-document clusters and named
hubs including Marcus Chen, David Okafor, Halcyon Retail Group, accounts,
merchants, invoices, statements, pay stubs, and 1099s. The export remains a
regenerable ignored artifact (`make graph-vault-extracted`), never the retrieval
backend or committed extraction evidence. Both ground-truth and extracted exports
target `exports/obsidian_vault`; identity is determined by the last target run and
the vault's `Source:` line, so use `make graph-vault` to restore the demo projection.

**Reproducibility boundary.** GraphML is committed, but LightRAG's
`vdb_entities.json`, `vdb_relationships.json`, and `vdb_chunks.json` remain
gitignored. A clean clone can re-derive the extraction score immediately, but must
run the approximately 45-minute `make graph-index` build before it can query C or
repeat the generation evaluation. Committing model-specific vector stores was
deliberately rejected in favor of the versioned build receipt.

**Why the Phase-15 verification receipts are retained.** The regenerated
`phase7_d0b6b7444eb3`, `phase9_judge_a40a6497095d`, and
`phase13_guardrails_6cf2b1ba4447` metrics are unchanged from their prior latest
runs. They are kept because Phase 15 added the `graph:` block and therefore changed
the config hash to `21a33d1b887e…`; together they prove the older gates still hold
under the Phase-15 configuration. Phase 14 discarded same-measurement verification
artifacts when they carried no equivalent configuration change. Each phase's
original close artifact remains committed and untouched; the new receipts add
configuration-regression evidence rather than replace history.

**Verification.** `make verify-track-a` exits 0 on the Phase-15 codebase: Ruff
clean; 152 tests passed; the 80-row golden set validates; the live Phase-7 gate is
10/10 rightly abstained plus the poisoned-document answer correct; the named
guardrail report stays green; judge validation is 20/20; retrieval regression is
`passed: true` with zero deltas. The Phase-15-specific deterministic run is also
green at 151 passed, 1 environment-dependent skip inside the restricted sandbox.
The review-fix closeout is separately green: `make lint` passes and `make test`
reports 153 passed, 1 environment-dependent skip.

**Trickiest piece (plain English).** A graph engine does not automatically produce
citations the product can verify. LightRAG returns graph context and internal file
references, while VaultLedger's safety boundary accepts only literal source
chunks with stable document and chunk IDs. The adapter therefore uses the graph
to choose evidence but resolves every result back to the original ingested chunk
before generation. That keeps the graph from becoming an unverifiable second
source of truth. The experiment then demonstrates the harder product lesson:
more connected context can cost more tokens, run slower, and in this six-row run
coincided with more safe abstentions without improving either reported answer
metric. C remains available for continued research, while B remains the
provisional default pending a powered comparison.

**Next:** Phase 16 — generate the cross-variant comparison and portfolio artifacts
without upgrading Phase 15's failed quality gates into successes.

## Phase 16 — Live documents, safely (opened and closed 2026-08-11)

ADR-0011 superseded the old next step above before Phase 16 code began: portfolio
work moves to Phase 19, while Phase 16 now builds the external live-document path.
ADR-0012 selects `ocrmypdf --skip-text` preprocessing and requires visible OCR
provenance. `PHASE16_BUILD_PLAN.md` translates both accepted decisions into the
implementation order and acceptance-test matrix.

**External-data boundary.** Typed `live.*` configuration now separates the user
inbox, derived index, LightRAG store, Obsidian projection, and query traces from the
synthetic/eval paths. The default is under `~/VaultLedger/`. App startup and every
live CLI operation resolve all five roots first and refuse any root at or below the
public repository. The roots may not contain one another. This is deliberately
stronger than gitignore: source PDFs, extracted text, graph data, projections, and
questions all stay outside the checkout.

**Real-PDF and OCR path.** Text-layer PDFs flow through the existing pdfplumber
offset/geometry parser without invoking OCR. Pages with near-zero text trigger
`ocrmypdf --skip-text`, write only to the external index, and are reparsed by the
same path. Missing `ocrmypdf` or Tesseract, a timeout, a non-zero exit, missing
output, or a still-unreadable page becomes an explicit failed document with no
chunks. Genuine layouts do not have to match the two synthetic extractors: typed
record extraction is best effort, while exact text remains available to retrieval.

**Provenance and eval isolation.** Document metadata stores corpus, document OCR
status, and OCR page numbers. Each chunk is marked from its source page, and the
citation verifier copies corpus/OCR status from the matched chunk rather than from
model output. The Library and Ask tabs visibly separate synthetic and user corpora;
an answer citing an OCR page shows a prominent warning to verify digits and table
columns against the original. Eval startup now rejects any user or OCR-derived
chunk even if someone points an eval command at the wrong index.

**Incremental watcher and graph.** `make live-ingest` runs a stability-gated inbox
scan and `make watch` runs a configured finite polling budget. The watcher requires
two identical size/mtime observations, persists processed fingerprints externally,
and re-ingests only changed files. A stable document id replaces its SQLite,
chunk/BM25, and Chroma rows. LightRAG receives one `ainsert` call; on a changed
document, its prior id is deleted before insertion. The live GraphML is projected to
the external Obsidian vault after each successful graph insert. Per-file stage
latency, model-call/token usage, and local cost status are appended to an external
JSONL receipt.

**Measured text-PDF smoke.** A generated invoice PDF was copied to an isolated
`/private/tmp` inbox and exercised against the installed `nomic-embed-text` and
`qwen3:8b` models. The complete parse → SQLite/BM25 → Chroma → one-document
LightRAG → Obsidian path completed in **26.286 s**. Graph insertion took **25.240 s**
and recorded 2 completion calls, 3 embedding calls, 4,280 input tokens, 311 output
tokens, and `$0` API spend explicitly labelled `unpriced`. The graph projection
contained the document plus three entity notes. A live Variant-B answer correctly
returned the three landing-page builds, `$1,787.79` unit price, and `$5,363.37` line
amount with the exact source line as a verified `corpus=user`, `ocr_derived=false`
citation. Two preceding prompts asking only for the short total line safely
abstained when their citation did not survive the minimum-length verifier; they are
not counted as successful answers.

**Found on review: the provenance schema would have moved the synthetic corpus
hash.** `Chunk` gained `corpus` and `ocr_derived`, and the default serializer emits
them, so the next `make ingest` would have rewritten `chunks.jsonl` and changed its
`corpus_hash` from `ba7148a112191bc8…` to `2e9fb7631c411c98…` — while every core
chunk field stayed byte-identical and only two constant fields were added. Every
committed Phase-11 and Phase-15 receipt cites the old hash, so a reader comparing
receipts across the Phase-16 boundary would have seen a corpus that appeared to have
changed when only its serialization had.

Both halves of the fix are recorded rather than one: chunk writers now use
`model_dump_json(exclude_defaults=True)`, which restores `chunks.jsonl` to
`ba7148a112191bc8…` byte-for-byte, and this note explains why the serialization is
customized. `Chunk`'s six content fields are required and therefore always emitted;
only `corpus`/`ocr_derived` can be omitted, and only when they equal the synthetic
defaults a reader already assumes. User chunks carry a non-default `corpus`, so their
provenance is always written and `assert_evaluation_corpus` still sees it. Two tests
pin both halves.

Also found on review: the OCR page threshold was restated as a literal in both
`parse.py` and `ocr.py`. They agreed, but a drift in either would OCR a page without
marking it `ocr_derived` — a silent ADR-0012 provenance failure no downstream check
catches. It is now the shared `MIN_PAGE_TEXT_CHARS` constant, with a test.

**Verification.** `make lint` is clean and `make test` is green at **167 passed**,
including 13 Phase-16 tests for path refusal, OCR gating/failure, provenance, eval
exclusion, incremental replacement, watcher stability/persistence, single-id graph
insertion, and UI warnings.

**Scan acceptance arm — run, and now green.** `ocrmypdf 17.10.0` and
`tesseract 5.5.3` were installed, closing the gap this entry previously recorded as
pending. A genuinely image-only PDF was generated — a rendered bank statement with
a slight skew, carrying **0 extractable characters**, so `needs_ocr` was `True` on a
real file rather than a stub. It was dropped into the shipped default inbox
(`~/VaultLedger/Inbox`) and run through `make live-ingest`, exercising the real
configuration rather than a test fixture path.

The complete ADR-0012 chain is now measured end to end:

  parse_ocr 2,988 ms (real ocrmypdf --skip-text), total 29,052 ms
  receipt: ocr_derived: true, ocr_pages: [1], corpus: user
  graph insert 24,997 ms — 2 completion + 3 embedding calls, 4,012 in / 258 out,
    $0 pricing_status: unpriced
  live answer: "The closing balance ... was $10,794.88" — correct
  its citation: doc=scan_statement page=1 corpus=user ocr_derived=True

OCR read every field of that statement correctly: all four amounts, the masked
account number `****4021`, both period dates, and both names.

**What that does and does not establish.** It establishes that the pipeline works:
an image-only document is detected, OCR'd, chunked, indexed, graphed, retrieved,
answered, and cited **with its OCR provenance intact all the way to the citation**.
It does **not** establish that OCR is reliable. This was one cleanly *rendered*
page, which is far easier than a photographed, faxed, or low-contrast statement —
the conditions under which OCR actually misreads digits. One clean pass is not an
accuracy measurement, and no OCR accuracy claim is made. ADR-0012's residual risk
stands undiminished.

**Isolation held under a real live run.** After ingesting a user document, the
synthetic corpus hash is still `ba7148a112191bc8…`, `assert_evaluation_corpus`
refuses the live index by name, the synthetic index is still accepted, and
`git status` is empty — the live run wrote nothing inside the repository.

**Trickiest piece (plain English).** A citation cannot discover that OCR read a
printed digit incorrectly; it can only prove the model copied the extracted text.
The implementation therefore treats OCR status like evidence provenance, not an
ingest log detail: the flag follows the exact page into the chunk, follows the
verified chunk into the citation, and reaches the user at the same place as the
number. That does not repair a wrong digit. It makes the residual risk visible and
keeps unlabelled OCR text out of every reported metric.

**Phase 16 is closed.** Every acceptance row in `PHASE16_BUILD_PLAN.md` is
discharged, including the scan arm, and unlike Phase 15 this phase needs no waiver:
its criteria were met rather than missed. ADR-0010's clause that the Phase-15 waiver
"does not authorize closing Phase 16 ... on a failed gate" is honoured literally —
the gate was run, not excused.

**Next:** Phase 17 — browser-UI packaging and handoff per ADR-0011: demo video,
one-click launcher, Ollama first-run flow, and a setup README for a non-technical
recipient. Note for that phase: `ocrmypdf` and Tesseract are now a **second install
dependency** for any recipient who wants scanned-document support, which is the
open packaging question ADR-0012 deliberately left unsettled.

## Phase 17 — Browser-UI packaging and handoff (opened 2026-08-11; in progress)

**What is now shipped.** `Launch VaultLedger.command` is a Finder entry point backed
by a standard-library bootstrap. It finds Python 3.11+, creates and fingerprints a
private `.venv`, installs the product extras and spaCy model with visible output,
checks Ollama, visibly pulls the pinned `nomic-embed-text` and `qwen3:8b` models, and
opens Streamlit on loopback only. A PID/health receipt makes a second double-click
reuse the live process, a setup lock prevents duplicate first-run work, and a bounded
port scan moves off 8501 rather than taking over an occupied listener. Missing Ollama
opens the official macOS download page and stops with instructions. Missing OCR is a
visible optional-capability warning: text PDFs keep working and scans still fail
closed through the Phase-16 path.

The launcher and normal `make run` path now bind to `127.0.0.1` and disable the file
watcher. `make doctor` reports **7 required checks plus one optional OCR capability**;
an absent OCR tool does not incorrectly fail text-PDF readiness. The non-technical
README leads with download size, expected first-run time, Finder steps, external
inbox location, local-processing boundary, and the scan/OCR limitation.

**A crash found only by exercising the real handoff path.** The development
environment had resolved Streamlit 1.59.1 with PyArrow 25. That pair segfaulted in
PyArrow dataframe serialization on the second live Streamlit rerun. The clean
environment instead resolved Streamlit 1.61.1 and PyArrow 24 and reran cleanly.
Runtime requirements now pin `streamlit>=1.61,<2` and `pyarrow>=7,<25`; launcher
schema `phase17-v2` invalidates an older environment, and its readiness probe enforces
the same versions. Two consecutive clean-environment AppTest renders report zero
exceptions.

The live walkthrough also exposed a UI-state defect: choosing the measured
credit-score example changed the selectbox but left the previous question in the
text field. The question field now has one stable key and a pure state transition
that resets only when corpus/example changes, preserving deliberate custom edits on
ordinary reruns. A regression test pins both behaviours.

**Recorded product evidence.** The Finder launcher was double-clicked on the
development account and opened the real local browser app. A second double-click
reused the same PID and sole `127.0.0.1:8501` listener. The live `qwen3:8b` /
`B_hybrid` answer returned Marcus Chen's March balance of `$4,207.55` with verified
statement/page/snippet evidence. The credit-score example returned `I couldn't find
that in your documents.`, no citation, and confidence `0.00`. The user Library view
showed its external inbox and explicit separation from synthetic metrics. The
112.5-second H.264 artifact is committed as
`demo/vaultledger_phase17_demo.mp4`; its SHA-256 is
`f54d4139c682392b34fe021bce0d1270b3bcc54c9758e3bad6d457545ac9a8e4`.

**Clean-environment and verification evidence.** A new Python 3.14.6 virtual
environment outside the repository installed `.[rerank,gateway,graph]` plus
`en_core_web_sm` from scratch. `pip check` reported no broken requirements, the
runtime import probe passed, and its 1.9 GB size matched the README estimate. The
command/output receipt is `receipts/phase17_clean_install.md`. On the development
account, `make doctor` reports 7/7 required checks and 1/1 optional capabilities;
`make lint` is clean; `make test` reports **178 passed, 1 environment-dependent
skip**. The synthetic `data/index/chunks.jsonl` SHA-256 remains exactly
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`.

**Machine half — still required and not yet proven.** This Mac had no spare standard
user account. Creating one changes an OS security/account setting and requires the
owner's approval plus administrator authentication, so the development-account run
is not relabelled as the kickoff brief's recipient-half proof. The receipt records
this open gate. Homebrew, OCRmyPDF, and Tesseract are system-wide on this Mac; even a
future clean-user pass will not prove the optional OCR setup from a Mac without
Homebrew, and that gap remains explicit.

**Human half — attempted as far as the available people allowed, with no finding to
invent.** No independent non-technical reader was available for the five-minute cold
read. The README and receipt say so plainly; the hiring manager remains the first
human usability test.

**Phase 17 remains open.** Every code, artifact, clean-virtualenv, and development-
account browser gate is green. Closure still requires the fresh standard-macOS-user
machine half. No waiver has been applied and no fresh-Mac claim is made.

### Phase 17 review continuation — code half complete; owner half still open

**Launcher acceptance repairs landed.** The ZIP quickstart and troubleshooting now
document Gatekeeper's one-time **right-click → Open → Open** path and state why it is
needed: the launcher is not code-signed under ADR-0011. When
`data/index/records.db` is absent, the launcher visibly runs the model-free
`python -m vaultledger.synth` and `python -m vaultledger.ingest --no-embed` path
before opening the app, so a fresh ZIP's first Library screen no longer depends on
the reader knowing a Make target. `KeyboardInterrupt` now exits 130 with the
requested cancellation message, malformed Ollama JSON is rendered as a readable
launcher error, and setup tears down any Streamlit child on cancellation. Ollama
detection probes the loopback service before looking for the optional CLI symlink,
checks `/Applications/Ollama.app` before declaring the app absent, and uses the
service pull API if models are missing but no CLI symlink exists.

**The four stale reader claims were corrected at their sources.** Regression now
raises on a manifest whose run id equals the frozen baseline id. `eval-full`
regenerates a full dense manifest and then a full B-hybrid manifest before running
regression, so the Phase-4 comparison and regression both compare compatible,
distinct runs. The canonical `reports/model_matrix.md` was regenerated from the two
full 80-row B-hybrid manifests (`61802221d874` / `33c0a0d50c76`), while Phase 14's
D-agentic cells now have their own `reports/phase14_agentic_matrix.md`; future
`agentic-eval` runs cannot overwrite the canonical matrix. The guard-on matrix was
also regenerated from its own committed cells. `make router-eval` is pinned to the
same two canonical B-hybrid answer receipts named by the README, and the router
generator now names Phase 18 rather than Phase 17. The matrix/config generator
strings use the same renumbering. Generated reports were regenerated through their
writers; none was hand-edited.

**Context truncation now keeps the best evidence.** Context assembly first selects
blocks in descending retrieval-score order, counts separators against the character
budget, skips an oversized block when a smaller later block can fit, and only then
applies the lost-in-the-middle edge ordering. The reproduced six-by-2,400-character
case now exposes ranks `1, 2, 3, 4` and drops `5, 6`; the old code exposed
`1, 3, 5, 6` and dropped ranks 2 and 4. A regression test pins the surviving-rank
set and the separator accounting. The 12,000-character default is now typed as
`generation.context_budget_chars` in `config.yaml`, rather than living only as an
answer-changing literal in `retrieve/context.py`.

**Track-A gate — first run red, then fixed and green; both outcomes retained.** The
first `make verify-track-a` run at `8cecd81` passed Ruff, **185 tests**, golden-set
validation, the live 11-case Phase-7 arm, guardrail evaluation, and the 20-label
judge run. It then failed after writing fresh B-hybrid manifest
`phase4_0f1681241cd3`: `_write_comparison` raised
`ValueError: baseline and Phase-4 run use different golden-set hashes` because the
Phase-3 comparison baseline still carried the pre-relabel golden hash. Exit was 2
after **160.2 s** wall time. That failure was not replaced with a green-only story.

The sequencing fix at `b69499a` adds the fresh full dense run before the fresh full
B-hybrid run. The second `make verify-track-a` exited **0** after **150.0 s**: Ruff
clean; **186 passed**; golden validation green; Phase-7 safety, guardrails, and judge
validation green; dense manifest `phase3_b45ca825de1a`; B-hybrid manifest
`phase4_e72bb7213548`; and regression `passed: true` against distinct frozen
baseline `phase4_551b3b20b9f9`. All four reported retrieval deltas were `0.0`; those
numbers are meaningful here only because the run ids differ. The synthetic chunk
hash was checked before the edits, after the code/test runs, after the failed gate,
and after the green gate; every check returned exactly
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`.

**The CI/local contradiction is now explicit.** CI was red for **seven consecutive
pushes** while this file recorded `make verify-track-a` green at the Phase-14 close
SHA (`62107bf`). Both statements were true: the local gate ran on a machine with a
built corpus, while CI first collected zero tests because the repository root was
absent from bare pytest's path and, after that fix, exposed four tests whose corpus
CI had never built. Nothing reconciled the two because nobody checked the Actions
history. Commits `56466d1` and `c9a3a61` fixed those separate failures. CI run
`31557816109` then reported 177 passed / 2 runtime-dependent skips and green; its
Ubuntu corpus build produced the same `ba7148a…5405` hash as macOS, the first
cross-platform observation of that byte identity. That is one observation, not yet
a reliability measurement, so CI still prints rather than gates on the hash.

**What did not land, and why Phase 17 remains open.** Part B belongs to the owner
and has not been performed: there is still no fresh macOS Administrator-account
install transcript and no `receipts/phase17_machine_half.md`. The pre-existing
development-account/clean-venv receipt is not relabelled as that evidence. Homebrew
and `Ollama.app` remain system-wide gaps, the Standard-user path remains untested,
and no independent non-technical cold read occurred. Checklist A5–A7 are explicitly
post-run findings and were not pulled forward. Phase 17 therefore remains **open**;
Phase 18 is not opened.

### Phase 17 close — on a waiver (ADR-0013), 2026-08-12

**Closed, not complete.** ADR-0013 records the owner's decision to close Phase 17
with its machine half deferred in full — including the ten-minute Gatekeeper smoke
test — to a single validation pass immediately before the product is shown to its
intended recipient. Checklist items A5–A7 travel with it.

**This is the weaker of the two waivers this project has taken, and the entry above
must not be read as equivalent to ADR-0010.** ADR-0010 waived a gate that was
*measured and missed*: Phase 15's entity recall was 73.3% against an 80% threshold,
and the number exists and is reported everywhere. ADR-0013 waives a gate that
**has not been attempted**. There is no observation to report, only an absence.

**What the phase did deliver, verified at close.** Bare `pytest` and `make test` both
**186 passed**; `make lint` clean; `make doctor` 7/7 required and 1/1 optional;
`make verify-track-a` exit 0 in 150.0s at `b69499a`; **CI green** at `cc212f0`; corpus
hash `ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405` unchanged.
Demo video committed and confirmed to show both a verified citation trail and a real
abstention. Launcher acceptance repairs, the four stale reader-facing claims corrected
at their generators, and the context-budget defect fixed with a regression test.

**One late repair, after the code half was reported complete.** The context budget had
been promoted out of a literal into `generation.context_budget_chars`, but bound at
*import* time, so `retrieve/context.py` read and parsed `config.yaml` as a side effect
of being imported and silently ignored any alternate config — measured: a config
carrying `context_budget_chars: 999` still assembled against 12000. Resolved on first
use instead (`71f5079`), `lru_cache`d because `load_config()` is uncached file I/O at
~2.3 ms on a per-query path. Importing the module now performs zero reads of
`config.yaml`, verified by spying on `builtins.open`. No fallback literal was added:
swallowing a config error would contradict this repo's own fail-loud rule.

**What is owed before handoff, and is not evidence yet.** No fresh macOS
Administrator-account install has been run. `receipts/phase17_machine_half.md` does
not exist. The clean-virtualenv receipt is **not** relabelled as that evidence, and
its own Homebrew gap is wider than it states — the "clean" venv was built from
Homebrew's Python (`/opt/homebrew/opt/python@3.14/bin`), while `/usr/bin/python3` on
this machine is 3.9.6, below the launcher's own ≥3.11 gate. The launcher's python.org
branch has therefore never executed. Homebrew and `/Applications/Ollama.app` remain
system-wide and uncovered by any same-machine account test. The Standard-user path is
untested. Checklist A5–A7 remain open. **No independent non-technical reader has
performed the five-minute README cold read**; neither the owner nor any agent
substitutes for it, and `README.md:56-62` continues to say so.

**The accepted risk, stated rather than minimised.** If Gatekeeper blocks the
documented ZIP → double-click path for a non-technical user, ADR-0011's browser-UI-
plus-launcher distribution decision reopens at handoff with no schedule remaining, and
its deferred alternative needs code signing and a paid Apple Developer account.
`README.md:33` and the launcher troubleshooting already document the one-time
right-click → Open path, so the expected failure mode is a documented extra step. That
expectation is reasoning, not a measurement.

**Status line that is accurate:** phases 0–16 closed; **phase 17 closed on a waiver
with named deferred work**. Any summary reading "phases 0–17 closed" without naming
ADR-0013 overstates it. Phase 18 opens next (`PHASE18_KICKOFF_BRIEF.md`).

## Phase 18 — Local-model bake-off and decoding sweep (opened 2026-08-12; in progress)

**The experiment is preregistered, but it has not been run.** ADR-0014 fixes the
six-model product matrix at `B_hybrid`, all 80 golden rows, guardrails on, seed 42,
and a fixed local `qwen3:8b` judge. It separately fixes the qwen3:8b factorial grid
at temperatures `{0.3, 0.7}` × top-p `{1.0, 0.9, 0.8}`, with the current
`0.0 / 0.95` cell as the baseline and a conjunctive decision rule. The original
temperature-zero experimental cells were replaced before any sweep because top-p
is inert under greedy decoding; all six experimental cells now exercise sampling.
Smoke rows are explicitly excluded from the finding. No sweep cell or canonical
full matrix has run, and no model winner, decoding winner, null result, or latency
ordering is claimed here.

**The decoding promotion has the narrow check it requires.** Commit `ddb7ecb`
promoted temperature, top-p, seed, and context into typed configuration before any
experimental sweep. `receipts/phase18_decoding_defaults.json` compares the old
implicit qwen3:8b profile with explicit `temperature=0.0`, `top_p=0.95`, and
`seed=42` on the same pre-parity `/api/generate` path. Both outputs hash to
`b226be22d7d5d5c6c76c72a8a94432dc993d804376e29ffb2597246855196c4a` and are
byte-identical. That byte result is confirmatory, not discriminating: temperature
zero is greedy and the probe's `const` schema permits only one answer. Behaviour
cannot change from making top-p explicit at greedy temperature; the separate reason
for choosing `0.95` is the script's fail-loud cross-check against qwen3:8b's
installed `/api/show` parameter. The receipt does not claim the later transport
change is neutral.

**Product and evaluation now call one actual system.** ADR-0015 and the shared
native `/api/chat` payload remove the old product `/api/generate` versus eval-chat
split. Product, matrix, judge, agent, and graph paths receive the same temperature,
top-p, fixed `top_k=20`, seed, `think=false`, context, and structured-output cap. The
refreshed live
parity receipt at `61cc61f` records `num_ctx=8192`, `num_predict=768`, and a
600-second request ceiling; product and eval outputs are again byte-identical at
`c1f33eaf44913dcb7c88f4df37c46170143de0756f79c9095c7d99b1b56d3664`, with
native provider counts of 41 input and 7 output tokens.

**A mechanics smoke changed the fixed capacity control before the experiment.** At
`num_ctx=32768`, qwen3:14b could not finish the first structured row within the
bounded request even after model pre-warming; those attempts remain temporary
diagnostic receipts and are not scored as quality failures. The assembled retrieval
context is capped at 12,000 characters, so ADR-0014 now fixes `num_ctx=8192` for
every model rather than granting the 14B model an exception. Under that common
window the same qwen3:14b row completed, and a fresh six-model N=1 smoke completed
all six candidate rows plus all six judge calls. The smoke's four pass and two fail
judge labels are discarded as experiment evidence; they establish runner mechanics
only. Candidate pre-warm time is outside row latency, installed identity is read
from Ollama `show`/`tags`, and resident/VRAM bytes are captured from `ps` while the
candidate is loaded.

This common-window decision also moves the live LightRAG path from its Phase-15
`num_ctx=32768` implementation to `8192`. The committed Phase-15 receipts and waiver
remain historical evidence about the old system; current Variant-C runs can truncate
LightRAG's independently assembled global context earlier and must not be described
as reproducing those Phase-15 numbers without a new measurement.

**The six exact tags are installed.** The pinned lineup is qwen3 4B/8B/14B and
gemma3 1B/4B/12B. Ollama reports `Q4_K_M` for each, parameter labels of 4.0B, 8.2B,
14.8B, 999.89M, 4.3B, and 12.2B respectively, and distinct installed digests. The
harness refuses missing identity/resource fields rather than substituting tag names
for parameter counts.

**Generated evidence is now the only reporting path.** Each cell writes its decoding
profile, model metadata, candidate usage, fixed-judge verdict and human-readable
reason into its RunManifest. Resumable checkpoints include the full population and
decoding key; incomplete judge coverage retains the checkpoint and fails loudly.
The report surfaces all failed reasons plus representative passes, calls the judge's
20-label validation weak evidence, and describes strict matching as a literal-anchor
scorer rather than a lower bound. The manifest-generated frontier uses latency,
judge/strict quality, generation coverage, resident-byte bubble area, family styling,
and direct labels;
visual QA caught and fixed axis/label collisions before any canonical artifact was
written. Its embedded caveat says it is descriptive, not a latency ranking, and
warns that latency excludes failed rows so points below 100% coverage are not
comparable on the x axis.

**Kickoff verification.** After the review fixes, sandboxed `make test` reports
**194 passed, 1 environment-dependent skip** and `make lint` is clean; the generated
SVG parses as XML and was visually
checked after the label repair. The synthetic chunk corpus remains exactly
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`. Phase 17's
deferred machine half was not performed or relabelled. The unrelated untracked
`Untitled` file was not touched.

**Next:** run the committed full 6 × 80 model matrix, inspect failed judge reasons,
then run the seven-profile qwen3:8b baseline-plus-grid comparison and apply the
preregistered rule. Only after those receipts exist should Phase 18 update the
reader-facing model recommendation, run `make verify-track-a`, and verify pushed CI.

### Phase 18 review corrections — 2026-08-13

**Two masked code defects were reproduced and repaired.** Importing
`vaultledger.retrieve` first closed a cycle through the generation package, and
`LightRAGRetriever.from_config()` passed two arguments its constructor did not accept.
The shared Ollama payload builder now lives in a dependency-free leaf module. The
retriever accepts, stores, and forwards both the 768-token output cap and 600-second
timeout to its live LightRAG binding. Fresh-interpreter import, config construction,
and live-binding forwarding each have a regression test; Variant C no longer depends
on import order to start.

**The experiment contract was corrected before data collection.** ADR-0014 records
why two greedy-temperature cells had no discriminating power and replaces them with
`top_p=0.8` at temperatures 0.3 and 0.7. `top_k=20` is a fixed typed control in all
product, matrix, judge, agent and graph requests and is present in new decoding
profiles. The refreshed default receipt labels its byte comparison as confirmatory
and records that the fail-loud `/api/show` checks observed `top_p=0.95` and
`top_k=20`; the refreshed product/eval receipt retains identical output hashes with
the new fixed control in both requests.

**The frontier now exposes its second latency limitation.** Every point label and
tooltip carries generation coverage. The embedded caveat states that latency is
computed over completed rows only and that a point below 100% coverage is not
comparable on the x axis. Tests count one structured labelled group per manifest and
check label coordinates against the SVG viewBox rather than pinning canvas pixels.

**Review verification.** The local `make verify-track-a` gate exited 0: Ruff clean;
**195 passed** with Ollama available; golden validation green; Phase-7 manifest
`phase7_94fa23ee07df`; guardrail manifest `phase13_guardrails_74041b883bb6`;
20/20 judge validation in `phase9_judge_3b376d88632e`; dense retrieval manifest
`phase3_d21af4c96a22`; B-hybrid manifest `phase4_9907de138ee3`; and regression
`passed: true` against the distinct frozen baseline. Sandboxed `make test` records
the same suite as 194 passes plus its one Ollama-dependent skip. The corpus hash
remains exactly `ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`.
No full six-model cell or decoding-sweep cell ran during this review.

### The six-model matrix has run — 2026-08-13

**The bake-off is measured, and it did not displace `qwen3:8b`.** All six preregistered
cells completed: 80 golden rows each, `B_hybrid`, guardrails on, seed 42, one identical
decoding profile per candidate, fixed local `qwen3:8b` judge. **100% generation coverage
on every cell and zero `TOOL_ERR` across all 480 rows.** Wall time 8,957 s (2.49 h).
Cost `$0.00` — unpriced, not free. ADR-0016 records the decision; the decoding sweep has
still not run.

| model | judge | strict | citation | abstention | median | p95 |
|---|---|---|---|---|---|---|
| gemma3:12b | 72% | 54% | 68% | 72% | 31.9 s | 57.3 s |
| **qwen3:8b** | **70%** | 44% | **71%** | **76%** | **7.2 s** | **13.3 s** |
| qwen3:14b | 64% | 46% | 62% | 66% | 27.0 s | 46.8 s |
| gemma3:4b | 56% | 41% | 56% | 61% | 4.6 s | 9.0 s |
| qwen3:4b | 52% | 34% | 48% | 50% | 4.0 s | 9.9 s |
| gemma3:1b | 26% | 8% | 20% | 24% | 1.9 s | 4.0 s |

**Plain-English explainer of the trickiest piece — why that table is the wrong way to
read the result.** Ranked by judge pass rate, `gemma3:12b` "wins" by two points. But
every model answered *the same 80 questions*, which means the right question is not
"what were the two totals" but "on which individual rows did they actually disagree, and
which way did those rows fall". They disagreed on ten rows: `gemma3:12b` got six of them
right where `qwen3:8b` failed, and `qwen3:8b` got four right where `gemma3:12b` failed.
Six versus four out of ten is what a fair coin looks like. The exact paired test
(McNemar) puts it at `p = 0.754` — no detectable difference. The two-point gap in the
totals was never two points of quality; it was one and a half rows of noise, and the
aggregate table hid the fact that only ten rows carried any information at all.

Run against `qwen3:8b`, the paired verdicts are: gemma3:12b 6 wins / 4 losses
(`p = 0.754`), qwen3:14b 3 / 8 (`p = 0.227`), gemma3:4b 2 / 13 (`p = 0.007`), qwen3:4b
5 / 19 (`p = 0.007`), gemma3:1b 1 / 36 (`p < 0.001`). Five comparisons, so under a
Bonferroni threshold of α = 0.01 the three significant losses hold and the two nulls are
unaffected.

**Two findings beyond the headline.** Scaling within a family did not help: `qwen3:14b`
lost 8 rows and won 3 against `qwen3:8b`, nominally worse on every quality metric at
3.75× the latency and 3.7 GB more resident memory. And `gemma3:1b` is unusable for this
product at 26% judge / 8% strict — the one large, unambiguous effect in the run.

**What is deliberately not claimed.** `p = 0.754` is absence of evidence, not evidence
of equivalence; ten discordant pairs give low power and only a large effect would have
surfaced. The judge remains weak evidence — its 20-label validation supports only an
at-least-83%-accurate claim and a null classifier scores 19/20 on that set — and the
paired test inherits any systematic bias in it. The strict-match column is confounded
with verbosity: mean answer length and strict rate rise together across all six models
(37 → 72 characters, 8% → 54%), and `strict_answer_match` is a literal-anchor scorer, so
`gemma3:12b`'s 10-point strict lead is not a 10-point correctness lead. No latency
ranking is claimed, and Phase 13's ~50% run-to-run p50 movement was **not** re-measured
here — each cell ran exactly once, so that caveat stands on its prior evidence, not on
anything observed today. What this run does show is large row-to-row spread inside a
cell (`qwen3:14b` 188 s max against a 27 s median; `gemma3:12b` 185 s against 31.9 s)
with no systematic drift across a cell — first-40 versus last-40 row means give ratios
of 0.65–1.04. Because medians hide that tail, p95 travels beside median everywhere.

**The most actionable result is not about models.** Of the ten rows separating the top
two candidates, **five are `FALSE_ABSTAIN`**: the system declined to answer when the
reference answer was available. That is consistent with the two known-open defects —
abstention fires whenever zero citations survive, and `verify_citations` only confirms a
snippet *exists*, never that it *supports* the answer. Model choice moved two points on
this corpus. The abstention policy is plausibly worth more than that, and it needs its
own pass rather than being folded into Phase 18.

**Per-category winners differ, and the router was deliberately not refitted.**
`gemma3:12b` leads `multi_hop` (50% vs 42%) and `adversarial` (50% vs 38%); `qwen3:8b`
leads `single_doc` (89% vs 83%) and ties `cross_persona` at 100%. Category cells hold
6–18 rows, so these are single-digit differences on tiny samples. Per the Phase 18
kickoff brief this is noted and **not** used to fit ADR-0004's routing map — fitting a
map to the same rows that produced it is not a held-out justification. Separately,
`unanswerable` reads 100% for five of six models and should be treated as a floor:
abstaining wins that category for free, which is why `gemma3:1b` scores 80% there while
scoring 26% overall.

**Next:** run the preregistered seven-profile `qwen3:8b` decoding comparison (~1–2 h) and
apply the ADR-0014 rule, then re-run `make verify-track-a` and verify pushed CI.

### The decoding sweep has run — it is null — 2026-08-13

**No preregistered cell met the rule, so `temperature=0.0 / top_p=0.95` is retained.**
All six experimental cells completed: 480 rows, 100% generation coverage on every cell,
zero `TOOL_ERR`, 8,320 s (2.31 h), `$0.00` unpriced. Every cell finalised with complete
judge coverage and no checkpoint was retained. ADR-0017 applies the ADR-0014 rule as
written; that rule was committed before any cell ran.

| profile | judge | strict | numeric | citation | abstention | identical | W/L |
|---|---|---|---|---|---|---|---|
| **0.0 / 0.95 (baseline)** | **70.0%** | 43.8% | 35.7% | 71.2% | 76.2% | — | — |
| 0.3 / 1.0 | 68.8% | 43.8% | 35.7% | 71.2% | 77.5% | 95% | 0/1 |
| 0.3 / 0.9 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 98% | 0/2 |
| 0.3 / 0.8 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 96% | 0/2 |
| 0.7 / 1.0 | 68.8% | 43.8% | 35.7% | 71.2% | 76.2% | 90% | 0/1 |
| 0.7 / 0.9 | 67.5% | 43.8% | 35.7% | 71.2% | 76.2% | 89% | 0/2 |
| 0.7 / 0.8 | 67.5% | 43.8% | 35.7% | 72.5% | 77.5% | 88% | 0/2 |

AC1 required a gain of at least four rows on **both** the strict scorer and the judge.
No cell gained a single row on either.

**Plain-English explainer of the trickiest piece — how to tell a real null from a broken
experiment.** A null result is only worth reporting if you can show the thing you varied
actually did something. Here it did: the share of answers byte-identical to greedy falls
cleanly as temperature rises — 98% at the tightest setting down to 88% at temperature 0.7
— so by the last cells roughly one answer in ten is worded differently. The sampling
knob was demonstrably live. And yet **all seven profiles pass exactly the same 35 rows**
on the strict scorer: not merely the same count, the same row identities, symmetric
difference zero. Numeric exact-match never moves off 15 of 42 either. So the experiment
reworded a tenth of the answers and changed the score on none of them. That combination —
visible change in the input, zero change in the outcome — is what separates "decoding
does not matter for this task" from "the sweep was misconfigured and nothing varied". The
reason is upstream: correctness is fixed by what retrieval puts in the context and what
the JSON schema permits, and with a mean answer length of 47 characters there is barely
any sampling entropy left for decoding to spend.

**Every cell drifted slightly worse, and that is recorded rather than hidden.** Across
the six cells there are 10 discordant judge rows, and all 10 favour the baseline; zero
favour any sweep cell. The cells share a baseline and the same rows, so they are not
independent and a pooled p-value would overstate it; no individual cell is significant
(`p` = 0.500 or 1.000 throughout). It is weak evidence in the direction theory predicts —
greedy takes the argmax, so on an extraction task a deviation is likelier to hurt than
help.

**Boundaries.** One model, one corpus, one seed, 80 synthetic rows, and a judge whose
20-label validation supports only an at-least-83%-accurate claim. This does not
generalise to the other five models, to user documents, to OCR-derived chunks, or to
tasks with long free-text answers where sampling has more room to act. The decoding
controls stay in typed config and in every `DecodingProfile`, so the comparison is
repeatable elsewhere.

**Both Phase 18 experiments are now honest nulls with mechanisms behind them.** The model
axis: nothing beat `qwen3:8b`, three candidates were significantly worse, and the two
that tied cost 3.7–4.4× the latency. The decoding axis: nothing beat `0.0 / 0.95`, and
all six alternatives drifted marginally worse. The shipped configuration survived contact
with evidence on both axes — a materially stronger claim than never having tested it, and
a weaker one than "best available", which is still not established.

**The open lead is unchanged and now doubly evidenced.** `FALSE_ABSTAIN` accounted for
five of the ten rows separating the top two models, and it appeared again in the sweep at
`gs_005`, where the baseline abstained and temperature 0.3 answered. Decoding moved zero
rows; abstention keeps moving rows in both experiments. It is the strongest remaining
lever and it needs its own pass, not a Phase 18 addendum.

**Next:** re-run `make verify-track-a`, push, and verify CI with `gh run list`. Then
Phase 18's reader-facing surfaces (README, app copy) can be updated to the
measured claim, and Phase 17's deferred machine half remains owed before handoff.

## Phase 18 close — 2026-08-13

**Phase 18 is closed with every acceptance criterion met, and no waiver.** Two of the
last three phases needed one — ADR-0010 waived a measured-and-missed gate for Phase 15,
ADR-0013 waived an unattempted one for Phase 17. Phase 18 needed neither, and neither
did Phase 16.

All ten criteria from `PHASE18_KICKOFF_BRIEF.md`: six models pulled with `ollama show`
parameter count, quantisation and digest recorded per manifest; `temperature`/`top_p`
promoted to typed config with the promotion's evidentiary strength honestly restated;
`seed` reaching the generator; product and eval sharing one decoding path (ADR-0015);
the grid and decision rule committed before any sweep cell, and amended before data
collection when two cells were found degenerate; one `RunManifest` per cell with
harness-generated report and frontier; judge verdicts surfaced with `reason`; a written
finding including the nulls; and green gates.

**Verification.** `make verify-track-a` exit 0 at `5fd731c`: Ruff clean, 195 tests,
golden set ok at `b59ee2659a17`, safety `phase7_0491e01a7f51`, guardrails
`phase13_guardrails_1891b24f977b`, judge validation 20/20 in `phase9_judge_354978c78787`,
dense `phase3_9fd669484144`, hybrid `phase4_48b5719b6f30`, regression passed against a
*distinct* frozen baseline. **CI green on `03f96e5`** — run 31756788417, checked with
`gh run list`, not inferred. Corpus hash unchanged at
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405` throughout.

**What the phase actually bought.** Two preregistered experiments, roughly 4.8 hours of
local inference, 960 scored rows, zero `TOOL_ERR`, and two null results with mechanisms
behind them. The model axis is flat around the incumbent; the decoding axis is flat
outright. ADR-0011's prohibition is discharged to exactly the strength of the evidence.

**Status line that is accurate:** phases 0–16 closed; **phase 17 closed on a waiver with
named deferred work (ADR-0013)**; **phase 18 closed, both experiments null, no waiver**.
The model claim is *"measured against five alternatives; none beat it"* — never *"the
best available local model"*.

**What did not change and is still owed.** Phase 17's machine half was not performed or
relabelled: no fresh macOS Administrator-account install, `receipts/phase17_machine_half.md`
still does not exist, checklist items A5–A7 and the independent non-technical cold read
are still outstanding before handoff. Phase 15's recorded results travel forward
untouched, though ADR-0015's common `num_ctx=8192` means current Variant-C code no longer
matches the system that produced them.

**The next phase writes itself.** Decoding moved zero rows and model choice moved two,
neither significantly. `FALSE_ABSTAIN` accounted for five of the ten rows separating the
top two models and appeared again in the sweep. The abstention policy fires whenever zero
citations survive, on a verifier that only confirms a snippet *exists* rather than that it
*supports* the answer — so the system can retrieve the right page, fail to verify support,
and refuse a question it had already answered correctly. That is the largest known
remaining lever and the strongest candidate for Phase 19.

## Phase 19 — Final comparison, portfolio, and abstention pass (opened 2026-08-13; in progress)

**Entry gate.** Before Phase 19 edits, `make test` reported **195 passed**, `make lint`
was clean, and `data/index/chunks.jsonl` still hashed to
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`. Local
`main` was `5da26ea`, one commit ahead of `origin/main`; the last observed CI evidence
remains the green `03f96e5` run, not an inferred result for the unpushed close commit.
Eight pre-existing untracked eval receipts were left untouched. Phase 17's waived machine
half and human cold read remain owed exactly as recorded above.

**The first causal audit corrected Phase 18's mechanism hypothesis.** The new
`make abstention-audit` target joins the canonical Phase 18 `qwen3:8b` answer receipt to
the golden set, classifies the layer that finalized every answerable abstention, and
replays retrieval without making a generation call. The generated receipt is
`receipts/phase19_abstention_baseline.json`, tied to source manifest
`phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f`, its answer-file hash,
config hash `f8f9b3e473cf…`, and golden hash `b59ee2659a17…`.

Of 70 answerable rows, 19 finalized as abstentions: **15 were model-declared, three were
output-guard downgrades, and one was a deliberate query-injection block**. The guard
downgrades split into one citation-verification event and two numeric-verification
events. The judge called 15 rows `FALSE_ABSTAIN`. All 10 unanswerable rows abstained and
none was answered.

The retrieval-only replay is the key discriminator. **Zero of the 19** top rerank scores
fell below configured `rerank_tau=0.35`, so SPEC's existing low-confidence L2 retry would
not fire on any of them. An expected document was already in the six supplied chunks for
14/19 rows and entered by a doubled top 12 for 17/19. This does not prove a prompt change
will help. It does rule out “the citation verifier caused most of them” and “implement the
existing low-confidence trigger” as evidence-matched first interventions.

**ADR-0018 preregisters one candidate before any candidate output exists.** The candidate
adds one exact evidence-first decision block to the reliable-generation prompt and leaves
retrieval, exact-snippet citation verification, numeric verification, injection handling,
model, decoding, context, and loop budgets fixed. It must reduce deterministic and judged
false abstentions by at least four, produce paired judge net wins of at least four, keep
all 10 unanswerable rows abstained, preserve injection safety, citation hit ≥57/80 and
strict match ≥35/80, complete 80/80 rows with zero `TOOL_ERR`, and leave Track-A/CI/corpus
gates green. There is no second tuned prompt if it fails.

The inherited portfolio scope is not displaced: Phase 19 still owes the harness-generated
variant matrix, honest Pareto sequence or non-comparability finding, ADR index, demo v2,
PM-OS report/blog artifacts, and final regression/DoD truth table. If the prompt is
adopted, Phase 18's old-prompt matrices become historical and must be rerun or explicitly
narrowed before the final claims ship.

**Verification so far.** The audit generator completed against local Ollama retrieval;
its model-independent unit slice is **4 passed**. The complete kickoff slice is
**199 passed**, `make lint` is clean, `git diff --check` is clean, and the corpus hash is
unchanged. No Phase 19 generation candidate has run, no improvement is claimed, and the
phase is open.
