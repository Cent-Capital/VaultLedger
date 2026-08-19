# Handover

**For whoever takes ownership of this repository.** Written 2026-08-19 at commit `8492c25`.

Read this page first. It tells you what state the project is actually in, what is owed
before anything here can be called finished, and the four conventions that will bite you
if you do not know about them.

---

## 1. What this is

A local-first financial-document question-answering system. It ingests PDFs on the user's
own machine, indexes them three ways (dense vectors, BM25, an entity graph), and answers
natural-language questions with citations back to the exact source snippet. Nothing is
sent to a hosted model — there is no hosted path in the product at all (ADR-0003).

The product runs. But **the deliverable is the evaluation harness and the evidence trail**,
not the app. Every architectural claim in this repository is tied to a committed
`RunManifest` carrying the git SHA, config hash, golden-set hash, seed, model, and full
decoding profile that produced it.

## 2. Status, stated accurately

> **Phases 0–16 closed. Phase 17 closed on a waiver (ADR-0013). Phase 18 closed, both
> experiments null, no waiver. Phase 19 open.**

Do not shorten this to "phases 0–18 closed" — that overstates it, and `CLAUDE.md` says so
explicitly. The waiver is named because ADR-0013 waives a gate that was **never
attempted**, which is weaker than ADR-0010's waiver of a gate that was measured and missed.

### The measured headlines, with their caveats attached

| Result | Evidence | The caveat that travels with it |
|---|---|---|
| Hybrid retrieval beat the dense baseline: recall@20 `0.9587 → 0.9786`, MRR `0.4974 → 0.7856` | `phase3_c2a1ee76001e`, `phase4_1966922cebd9` | Over the 70 answerable rows of 80. High recall is a property of a 60-document corpus at k=20, not a claim about a real library. |
| Agentic RAG (Variant D) beat hybrid on its target categories | Phase 14 receipts | **On `qwen3:8b` only.** It regressed on `qwen3:4b` (−25.0 pp aggregation). "Variant D beats Variant B" without naming the model is false. |
| Six-model bake-off: nothing beat `qwen3:8b` | ADR-0016, six `phase18_*` manifests | The claim is *"measured against five alternatives; none beat it"* — **never** "the best available local model." `p=0.754` is absence of evidence, not equivalence. |
| Decoding sweep: nothing beat `temperature=0.0 / top_p=0.95` | ADR-0017 | All seven profiles pass exactly the same 35 strict rows. A null, with the mechanism shown. |
| GraphRAG (Variant C) entity recall | ADR-0009, ADR-0010 | **11/15 = 73.3%, which MISSED the preregistered 80% gate.** Precision is 13.6% and the extractor fabricated account identifiers from a ZIP code and a paycheck amount. C is **not** promotable. |
| Guardrail cost | Phase 13 ablation | The full guard stack costs **one row out of eighty** on 8B and nothing on 4B. |
| Injection resistance | `phase7_*` manifests | `injection_pass_rate 1.0` over **11 examples** — 10 unanswerable plus one poisoned document. Not a general safety claim. |
| Over-refusal | Phase 13 guardrail eval | **0 of 6, and not meaningfully tested.** Never write "≤5% achieved" — at n=6 a clean sweep only bounds the true rate at 39.3%. |
| API spend | every manifest | `$0.00` — **unpriced, not free.** Phase 18 alone spent 4.8 hours of local inference. |

## 3. Four conventions that will bite you

**1. `PROGRESS.md` is append-only.** Its own header says *"No backdating, no compressing —
the commit history is the receipt."* Add entries at the end. Do not rewrite, summarise, or
reorder what is there. A navigation index was added at the top on 2026-08-19; it is
clearly marked and alters no entry.

**2. ADRs are amended, never rewritten.** ADR-0003 and ADR-0004 both carry amendments that
withdraw their own earlier reasoning. That is the intended pattern — append an
`## Amendment` section with a date, leave the original text standing.

**3. `reports/` is load-bearing, not clutter.** Its ~200 files are hard-coded as default
paths in `vaultledger/evals/run.py`, `variant_matrix.py`, and `failure_pareto.py`, are
named inside source-hashed receipts, and are asserted by tests. **Do not reorganise this
directory.** Individual run ids are cited by name across the ADRs; moving or renaming a
file silently invalidates the artifact that cites it.

**4. Generated reports are never hand-edited.** `reports/model_matrix.md`,
`variant_matrix.md`, `failure_pareto.md`, `adr_index.md`, `guardrail_eval.md` and the
frontier SVGs are produced by their generators from committed manifests, and tests assert
this. If a number is wrong, fix the generator and regenerate.

## 4. What is owed before this can be called done

These are carried forward explicitly in the build log. None is resolved.

**Blocking the handoff itself:**
1. **Phase 17's machine half has never been run.** No fresh macOS Administrator-account
   install; `receipts/phase17_machine_half.md` does not exist. Checklist items A5–A7 in
   `docs/briefs/PHASE17_CLOSE_CHECKLIST.md` travel with it. The clean-virtualenv receipt
   is **not** that evidence and must not be relabelled as it.
2. **No independent non-technical reader has done the five-minute README cold read.**
   Neither the previous owner nor any agent substitutes for it.
3. **The launcher's python.org branch has never executed.** The "clean" venv was built from
   Homebrew's Python; `/usr/bin/python3` on the build machine is 3.9.6, below the
   launcher's own ≥3.11 gate. A brand-new account would exercise exactly that untested path.
4. **Gatekeeper risk is unverified.** If macOS blocks the documented ZIP → double-click
   path, ADR-0011's distribution decision reopens. The expected failure mode is a
   documented extra step — *that expectation is reasoning, not a measurement.*

**Measurement debt:**
5. The **~60-case over-refusal probe set does not exist** (ADR-0005). Until it does,
   over-refusal stays "0 of 6, not meaningfully tested."
6. **Latency cannot rank models in this harness.** ~50% p50 movement between runs producing
   byte-identical answers. Needs repeated cells with a reported spread, pinned machine
   conditions, or a different x-axis (ADR-0003 amendment 2).
7. **Routing accuracy is "met in form only."** The labels are the policy serialised, and
   the category→tier map is contradicted by its own source data on **44 of 80 rows**
   (ADR-0004 amendment). A held-out routing set is owed.
8. `golden_hash` still hashes the whole golden-set file, so a metric-irrelevant edit will
   trip the regression guard again. Narrowing it needs its own ADR.

**Open product defects:**
9. **The citation verifier confirms a snippet *exists*, never that it *supports* the
   answer.** This is the largest known lever. Two preregistered attempts to close it were
   rejected (ADR-0019 on insufficient paired wins, ADR-0021 on 28 false positives across a
   1,040-row replay). The natural next candidate is a local entailment pass — stricter, not
   looser.
10. **Variant D answered an unanswerable question** (`ua_007`) and every guard passed it.
    Recorded, not fixed.
11. **The agent's `sql` tool fails 39–47% of planner calls.** It is secure; the planner
    cannot write queries it accepts.
12. **The empty-SQL-result logical defect is open.** Two model-facing wording attempts were
    rejected (ADR-0022, ADR-0024) and ADR-0023's stop rule forbids a third. It moves to
    schema work: comparing invoices and 1099s through an explicit person relationship.
13. **No Langfuse span has ever reached a Langfuse project.** The adapter's API usage is
    verified against the real SDK; delivery is not.
14. One `make run` process **exited with signal 11**, cause unknown, never reproduced.
    `torchvision` is absent while `transformers` expects it — an inconsistent dependency
    state in the same native stack. Explicitly not offered as a diagnosis.

**Deliverables not started:** demo v2, and the internship report and blog draft, which live
in a separate narrative workspace outside this repository.

## 5. Licensing and attribution — unresolved, deliberately

`LICENSE` reads *"Proprietary, all rights reserved… Created in connection with an
internship at Cent Capital LLC; not licensed for reuse."* It has **not** been changed as
part of this handover, because licensing is a legal decision for the owner and Cent
Capital rather than an editorial one. Resolve it before any external distribution.

Related: `CLAUDE.md` and `docs/briefs/PM_OS_HANDOVER.md` reference a private narrative
workspace on the previous owner's machine (`~/Desktop/PM-OS`). Those paths will not exist
for you. They are documentation of where non-code artifacts were routed, not a runtime
dependency — nothing in the build reads them — but you may want to genericise them.

## 5a. Pre-transfer checklist — things only the new owner can fix

Each of these hardcodes the *previous* owner's identity or asserts a fact that the transfer
itself will change. None is fixable without knowing the destination org.

| Item | Where | What it needs |
|---|---|---|
| The ZIP download link points at a personal account | `README.md:44` — `github.com/abhinavgupta0809/vaultledger/archive/…` | Repoint to the org URL. This is the **first link a non-technical recipient clicks**; if it 404s, the documented handoff path fails at step one |
| Same link, wiki copy | wiki `Getting-Started` page | Same repoint |
| The remote is asserted to be public in five places, but is currently **private** | ADR-0011 (×2), `README.md:14`, `PROGRESS.md:2259`, `docs/briefs/ROADMAP_RESEQUENCE_BRIEF.md:48` | Decide the destination visibility, then reconcile. Recorded as a dated observation at the end of `PROGRESS.md`; deliberately not edited in place |
| `LICENSE` — "Proprietary… internship at Cent Capital LLC; not licensed for reuse" | `LICENSE` | A legal decision, see §5 |
| Rounding drift between the ADR and its own artifact | ADR-0016 reads 72% judge and 8.0 GB resident; `reports/model_matrix.md` reads 72.5% and 7.50 GiB | Consistent (8.0 GB ≈ 7.45 GiB), different precision and units. Not an error — but a reviewer diffing the ADR against the generated artifact will query it |

**Do not "fix" the visibility assertions by editing ADR-0011.** ADRs are amended, not
rewritten. Add an `## Amendment — <date>` section if you want it corrected in the decision
record itself.

## 6. Getting running

See [`getting-started.md`](getting-started.md). The short version:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
make install
ollama pull nomic-embed-text && ollama pull qwen3:8b
make data && make ingest && make doctor      # doctor should report 7/7 + 1 optional
make test                                     # 238 tests
make run
```

`make doctor` is read-only and names the exact remedy for every failing check. Start there
before debugging anything.

## 7. Where to read next

| You want to | Read |
|---|---|
| Understand the system | [`architecture.md`](architecture.md) |
| Understand the metrics | [`evaluation.md`](evaluation.md) |
| Know what is *not* proven | [`limitations.md`](limitations.md) |
| Walk a decision | `decisions/` and the generated `reports/adr_index.md` |
| Read the full build history | `PROGRESS.md` — start with its index |
| See the original design | `SPEC.md` — **read its ACTIVE DEVIATIONS banner first**; eleven items in the body are superseded by ADRs |
