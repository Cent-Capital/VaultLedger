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

**Model performance notes (fill after Ollama pull, Phase 2)**
- Dev machine RAM: _TBD_
- `qwen3:8b` tokens/sec: _TBD_
- `qwen3:4b` tokens/sec: _TBD_

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
