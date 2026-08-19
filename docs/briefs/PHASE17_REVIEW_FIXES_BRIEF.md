# Phase 17 review — fix brief

Opened 2026-08-11 · For Codex · Follows the Phase 17 close at `02a6aa2`

Scope: four items only. Every one was **reproduced in the review session**, and the
exact command that reproduced it is given below so you can confirm the failure before
you change anything and confirm the fix after. Do not widen this brief — the deeper
findings (citation verification, guardrail population handling, agent time budget,
judge validation power) are real but are owed to their own pass, not this one.

**Entry state:** `make test` 179 passed · `make lint` clean · `make doctor` 7/7
required + 1/1 optional · tree clean · `main` is **ahead of `origin/main` by 1** and
has not been pushed.

---

## Update 2026-08-12 — items 1 and 5 have landed; 2, 3 and 4 are open

Items **1** (`56466d1`) and **5** (`c9a3a61`) were fixed and pushed while writing
this brief. **CI is green for the first time since at least 2026-08-10.**

One correction to what item 1 originally said. It claimed the `pythonpath` line
would make CI green. **It did not, and could not.** That fix was necessary but not
sufficient: it restored collection (0 tests → 179 collected), which then revealed a
second, older failure that had been hidden behind the collection error — four tests
reading a corpus CI never built. Item 5 was written after observing that. The
original text is left below as written, with the correction attached, because this
log does not silently rewrite claims that turned out to be wrong.

Entry state was also wrong on one point: the brief said no CI badge existed yet
because the commit was unpushed. In fact CI had failed on **seven consecutive
pushes** since 2026-08-10. That was inferred rather than checked, and `gh run list`
would have settled it in one command.

**Open for Codex: items 2, 3 and 4.**

---

## 1. CI runs zero tests — **LANDED in `56466d1`, but see the correction above**

**Reproduce:**

```
.venv/bin/pytest --collect-only -q
```

```
tests/test_phase17.py:12: in <module>
    from scripts import launch_vaultledger as launcher
E   ModuleNotFoundError: No module named 'scripts'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

`make test` runs `python -m pytest`, and `python -m` prepends the working directory
to `sys.path`, so `scripts` imports. `.github/workflows/ci.yml` runs bare `pytest`,
which does not. `pyproject.toml` declares `[tool.setuptools.packages.find] include =
["vaultledger*"]`, so the editable install never maps `scripts`, and there is no root
`conftest.py` and no `tests/__init__.py`.

A collection error aborts the **entire** run. On CI this commit executes **0** tests,
not 178. The local `make test` alias is what hides it.

**Fix** — add one line to the existing block in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
pythonpath = ["."]
```

**Verify:** `.venv/bin/pytest -q` (bare, not `python -m`) must report 179 passed.

**Measured after landing:** bare `pytest` 179 passed locally. On CI the collection
error was gone and the run reported `4 failed, 173 passed, 2 skipped` — the suite
executed for the first time, and the four remaining failures are item 5, not this one.

**Then extend the CI loop lint.** — done in `c9a3a61`. `.github/workflows/ci.yml`'s
"No unbounded loops" step greped `vaultledger/` only; `scripts/` is executable
product code (481 lines) and `app/` is the UI. Now greps `vaultledger/ scripts/ app/`.
No current violations.

---

## 2. Four stale reader-facing claims

These are documentation corrections. No behaviour changes. Item 2a is the one that
matters most: it is checkable in ten seconds and the repo's own PROGRESS entry
already published the rule that refutes it.

### 2a. The regression claim is contradicted by the artifact

**Reproduce:**

```
.venv/bin/python -c "import json; d=json.load(open('reports/regression_latest.json')); print(d['baseline_run_id'], d['current_run_id'], d['passed'])"
```

```
phase4_551b3b20b9f9 phase4_551b3b20b9f9 True
```

Current text, `README.md:82-83`:

> - The current retrieval regression report compares two distinct full pipeline
>   runs and is green. The deliberate negative-control report is red.

Baseline and current are the **same run**, so all four deltas are necessarily `0.0`
and the gate cannot fail. This is the exact defect `PROGRESS.md:855-857` already
caught and corrected once — *"the first version compared the baseline run against
itself, so every delta was necessarily `0.0` and the artifact proved only that the
file parsed"* — and `PROGRESS.md:877-879` states the rule: identical deltas *"only
mean something because the run ids differ."*

Root cause is not the README. `evals/run.py` defaults `--current` to
`reports/phase4_latest.json`, and `Makefile:48-53` `eval-full` runs `validate,
safety, guardrails-eval, judge-validate, regression` — it **never regenerates**
`phase4_latest.json`. So `verify-track-a` (`lint test eval-full`) re-reads a frozen
file and compares it to the baseline derived from that same file.

**Fix, in this order:**

1. Make `compare_manifest` raise when `current.run_id == baseline.source_run_id`.
   A self-comparison must be an error, not a pass.
2. Add a retrieval run to `eval-full` before `regression` so the gate compares two
   genuinely distinct runs.
3. Rewrite the README bullet to describe what is actually true after (1) and (2).
   If you run out of time for (2), the honest interim sentence is that the current
   regression artifact compares a run against itself and therefore proves only that
   the manifest parses — say that rather than deleting the bullet.

### 2b. The model-matrix sentence describes a file that was overwritten

Current text, `README.md:91-92`:

> The current [model matrix](../../reports/model_matrix.md)
> contains full 80-case `qwen3:4b` and `qwen3:8b` Variant-B runs.

`reports/model_matrix.md` says *"Cells: **2** across **2 model(s)**"* and its only two
rows are `D_agentic` at **N = 26**. The 80-case `B_hybrid` runs do exist as manifests
(`phase11_ollama_qwen3_4b_b_hybrid_61802221d874`,
`phase11_ollama_qwen3_8b_b_hybrid_33c0a0d50c76`, both `matrix_examples 80.0`), but
`Makefile:66-67` `agentic-eval` omits `--report`, which defaults to
`reports/model_matrix.md`, so Phase 14 overwrote the file the README points at. A
reader who clicks the link sees a different experiment.

**Fix:** give `agentic-eval` its own `--report reports/phase14_agentic_matrix.md`,
regenerate `model_matrix.md` from the B_hybrid cells, and only then leave the README
sentence as written. If regenerating is out of scope now, change the sentence to name
the two manifest ids directly instead of the overwritten file.

### 2c and 2d. Two stale phase numbers in generated reports

ADR-0011 renumbered the bake-off from Phase 17 to Phase 18. `PROGRESS.md` carries a
translation key; `reports/` does not.

- `reports/routing_frontier.md:21` — *"until Phase 17 repeats cells"*. Source is
  `vaultledger/evals/router.py:389`. Fix the generator string, then regenerate.
- `reports/model_matrix.md:3` — *"The full six-model bake-off is Phase 17."* Locate
  the generator (it is a static header in the matrix report writer; grep the literal),
  fix it there, then regenerate. Do not hand-edit a harness-generated file.

Also correct `vaultledger/evals/matrix.py:69`, whose docstring says *"until Phase 17's
judged bake-off"*, and `vaultledger/config.py:64` (*"bake-off has happened"* context —
check whether the surrounding sentence names a phase number).

---

## 3. Context assembly silently drops the best evidence

**Reproduce:**

```
.venv/bin/python - <<'PY'
import re
from vaultledger.retrieve.context import assemble_context, reorder_for_lost_in_middle
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk

def mk(rank, n):
    c = Chunk(chunk_id=f'd{rank}#c0', doc_id=f'd{rank}', page=1, text='X'*n,
              char_start=0, char_end=n, corpus='synthetic')
    return ScoredChunk(chunk=c, score=1.0-0.1*rank, rank=rank, source='hybrid')

hits = [mk(r, 2400) for r in range(1, 7)]
print('reordered order  :', [h.rank for h in reorder_for_lost_in_middle(hits)])
ctx = assemble_context(hits, budget_chars=12000)
seen = sorted(int(x) for x in re.findall(r'rank=(\d+)', ctx))
print('model actually saw:', seen)
print('dropped           :', sorted(set(range(1,7)) - set(seen)))
print('budget wasted     :', 12000 - len(ctx))
PY
```

```
reordered order  : [1, 3, 5, 6, 4, 2]
model actually saw: [1, 3, 5, 6]
dropped           : [2, 4]
budget wasted     : 2053
```

`vaultledger/retrieve/context.py:34` applies `reorder_for_lost_in_middle` **before**
enforcing the character budget. The reorder deliberately places rank 2 last and rank 4
second-to-last (`ranked[::2] + reversed(ranked[1::2])`), and the loop then `break`s on
the first block that does not fit. So the budget cut always eats the **highest-ranked**
chunks first, and `break` abandons the remaining budget instead of skipping to a
smaller block.

**Why this is worse than a ranking bug.** Nothing downstream notices.
`verify_citations` (`generate/reliable.py:512`) verifies against `hits`, not against
the assembled context, and `_confidence` (`generate/reliable.py:360-366`) reads scores
from `hits` too. The answer keeps full confidence, no `GuardrailEvent` is emitted, and
no trace field records that evidence was dropped.

**Reachability.** It does not fire on the committed synthetic receipts — corpus chunks
are small (median 364 chars). It fires on the **Phase 16 live/user-document path**,
where real PDFs produce chunks up to `chunking.max_chars=2400`, and on
`retrieve/agentic.py:514` (`assemble_context(provenance_hits, budget_chars=6000)`).
That is the path being handed to a non-technical recipient.

**Fix:**

1. Select the chunks that fit the budget **in score order first**, then apply
   `reorder_for_lost_in_middle` to the surviving set.
2. Count the `"\n\n---\n\n"` separator in `used`; it is currently uncounted.
3. Consider `continue` rather than `break` so a smaller lower-ranked block can still
   use leftover budget — but only after (1), since with (1) the truncation is already
   score-correct and `break` becomes harmless.

**Add a regression test** asserting that with N equal-size chunks and a budget that
fits M < N, the surviving ranks are exactly `1..M` in some order. The current suite
has no test that would have caught this.

**Constraint:** this must not move the synthetic corpus hash
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`. It should not —
`context.py` is read-side only and touches no chunk writer — but confirm with
`shasum -a 256 data/index/chunks.jsonl` before and after.

While here, promote `DEFAULT_CONTEXT_BUDGET_CHARS = 12_000` (`context.py:7`) to
`config.yaml`. It is a budget that bounds real work and silently changes answers, and
this repo's own rule is that every such knob routes through `config.py`.

---

## 4. Re-run the Track-A gate at the Phase 17 SHA

`README.md:69` cites `make verify-track-a` passing on **2026-08-04**. Since then
Phase 17 changed the Streamlit and PyArrow pins in `pyproject.toml`, and nothing has
been re-verified against those pins. No document currently claims otherwise, so this
is a gap rather than a false claim — but it is the gate this repo treats as
authoritative, and it should not be stale across a dependency change.

**Do this after items 1–3 land**, so the run covers the fixes:

```
make verify-track-a
```

Record the result in `PROGRESS.md` with the SHA and the wall time, in the same form as
the earlier entries. If it fails, that failure is the finding — report it, do not
re-run until green and quietly record the green one.

Note that until item 2a's fix (2) lands, the `regression` arm inside `eval-full` is
still comparing a run against itself, so a green `verify-track-a` does not yet mean
retrieval was re-measured. Say so in the PROGRESS entry.

---

## 5. CI never built the corpus — **LANDED in `c9a3a61`**

Added after item 1 restored collection and exposed this underneath it.

**The failure:**

```
FAILED tests/test_phase3.py::test_golden_expected_snippets_exist_in_current_chunks
FAILED tests/test_phase3.py::test_context_assembly_wraps_chunks_as_untrusted_data
FAILED tests/test_phase3.py::test_answer_question_returns_valid_local_answer_contract
FAILED tests/test_phase15.py::test_lightrag_inputs_preserve_one_document_id_per_source
E  FileNotFoundError: 'data/index/chunks.jsonl'
```

`data/index/` is gitignored derived data. These four tests could only ever pass on a
machine where someone had run `make data && make ingest`. They had **never** passed
on CI.

This is the same shape as the item 2 claims: `ingest/pipeline.py`'s module docstring
says `embed=False` is *"used by CI, which has no model runtime."* The capability was
built and documented for CI. **CI never called it.**

**What landed:**

- `python -m vaultledger.synth` then `python -m vaultledger.ingest --no-embed` before
  pytest. All four tests use fake retrievers and generators, so they need the chunk
  corpus and no model runtime.
- `python -m spacy download en_core_web_sm`. `make install` does this (`Makefile:9`)
  but CI pip-installs directly, and `PiiTagger.__init__` loads the model
  unconditionally at `pipeline.py:77`, so ingest would have failed without it.
- The corpus hash printed, **not** asserted.

**Measured on CI (`31557816109`):** `ingested 60 docs (0 failed), 60 chunks, vector
index SKIPPED`; `177 passed, 2 skipped`; green.

**New finding, worth a PROGRESS note.** The Ubuntu runner produced
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405` — **byte-identical
to the macOS build machine.** The "regenerates byte-identical from the seed" claim has
been in `CLAUDE.md` since Phase 1 and had only ever been observed on one platform.
This is the first cross-platform evidence for it.

**Do not gate on the hash yet.** One observation is not a reliability measurement.
Leave the step informational until it has held across several runs; then converting it
to an assertion is a genuinely strong invariant, because it catches the silent
receipt-orphaning drift this repo already worries about.

The 2 skips are the Langfuse and Ollama tests no-opping without credentials or a model
runtime. That is expected, but it means **CI proves less than the local 179** — worth
one honest sentence wherever the test count is quoted.

---

## Out of scope for this brief — do not fold in

These were found in the same review and are real, but each needs its own pass with its
own acceptance criteria:

- Citation verification confirms a quoted snippet **exists** in the retrieved set but
  never that it **supports** the answer; abstention fires only when *zero* citations
  survive. An answer stating a fabricated figure while quoting a real adjacent line
  ships at `confidence=0.91` with zero guardrail events.
- `numeric_verify` and `cross_persona_check` emit `action="pass"` when their typed
  record population is **empty**, which is the normal state in user-document mode.
- The agent time budget is polled at loop boundaries, not enforced on in-flight calls;
  `run_readonly_sql` has no statement timeout.
- `routing_accuracy = 100%` is a tautology: the router's only input is `category` and
  `expected_tier` is a pure function of `category`.
- `strict_answer_match` is described in generated reports as a *"deterministic
  lower-bound scorer"*; it scores a hedged answer listing five candidate figures as
  fully correct. It is not a lower bound.
- The judge's 20-label validation supports "≥83% accurate", not "1.00", and a null
  model with no LLM scores 19/20 on the same set.
- `launch_vaultledger.py`: `KeyboardInterrupt` during the 15–45 minute download
  escapes as a raw traceback; `find_available_port` lacks `SO_REUSEADDR` so a quick
  relaunch spuriously bumps to 8502; the README's ZIP-download path will likely hit
  Gatekeeper on an unsigned `.command`.

---

## Acceptance for this brief

- [x] Bare `.venv/bin/pytest -q` reports 179 passed (not just `make test`). — `56466d1`
- [x] CI loop lint covers `vaultledger/ scripts/ app/`. — `c9a3a61`
- [x] CI builds the corpus and the four index-reading tests actually run. — `c9a3a61`
- [x] **CI is green.** Run `31557816109`: 177 passed, 2 skipped.
- [ ] `compare_manifest` raises on a self-comparison; a deliberate self-compare fails.
- [ ] The four stale claims are corrected at their **generator**, and any affected
      report is regenerated rather than hand-edited.
- [ ] The context-budget reproduction above shows surviving ranks `1..M`.
- [ ] A new test fails on the old `context.py` and passes on the new one.
- [ ] `shasum -a 256 data/index/chunks.jsonl` still starts `ba7148a112191bc8`.
- [ ] `make verify-track-a` re-run at the Phase 17 SHA, result recorded honestly.
- [ ] `make lint` clean.
- [ ] A `PROGRESS.md` entry that states plainly which claims were wrong and for how
      long. Two of them survived a commit titled *"Pre-Phase-17 audit: correct two
      stale status claims"* — that is worth recording, not smoothing over. It should
      also record that **CI was red for seven consecutive pushes** while
      `PROGRESS.md` recorded `verify-track-a` green at the Phase 14 close SHA. Both
      were true — the gate passed on a machine with a built corpus and had never
      passed on CI — and nothing reconciled them because nobody opened the Actions
      tab. Note the cross-platform corpus-hash result from item 5 in the same entry.
- [x] **Push.** Done: `56466d1` and `c9a3a61` are on `origin/main`, along with the
      Phase 17 packaging commit `02a6aa2` that had been sitting unpushed. The GitHub
      ZIP the README points at now actually contains the launcher.
