# Phase 19 kickoff — final comparison, portfolio, and abstention pass

Opened 2026-08-13 · Implements ADR-0011 / SPEC §16 Phase 16 · Extends with ADR-0018

## Entry state (verified in this session, not assumed)

Phase 18 is closed with both preregistered experiments null and no waiver. Phase 17 is
closed **on ADR-0013's waiver**, with its fresh macOS Administrator-account machine half,
checklist A5–A7, and independent non-technical cold read still owed before handoff.

At entry, `make test` reported **195 passed** and `make lint` was clean. The synthetic
chunk hash remained
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`.
Local `main` was at `5da26ea`, one commit ahead of `origin/main`; CI was last observed
green at pushed commit `03f96e5`, not at the unpushed Phase 18 close commit. Eight
pre-existing untracked eval receipts were present and are not Phase 19 inputs or edits.

## What Phase 19 is — and is not

ADR-0011 moved SPEC's comparison/portfolio phase to Phase 19. That inherited scope does
not disappear because Phase 18 found a promising error bar. Phase 19 has two ordered
parts:

1. **One preregistered abstention-policy experiment**, because final artifacts should not
   freeze a known dominant failure without one bounded attempt to address it.
2. **The final comparison and handoff artifacts**: cross-variant matrix, historical
   Pareto sequence, ADR index, demo v2, blog/internship inputs, and final regression/DoD
   truth table.

This is not permission for iterative prompt tuning. ADR-0018 permits one candidate
prompt on the frozen 80 rows and fixes the decision rule before it runs.

## Work package 1 — diagnose before changing policy

The kickoff audit is implemented by `make abstention-audit` and written to
`receipts/phase19_abstention_baseline.json`. It joins the canonical Phase 18
`qwen3:8b` answer receipt to the golden set, classifies the layer that finalized each
answerable abstention, and replays retrieval only. It makes no generation or improvement
claim.

Measured baseline:

| Signal | Result |
|---|---:|
| Full population | 80 |
| Answerable / unanswerable | 70 / 10 |
| Answerable abstentions | 19 |
| Model-declared / guard downgrade / query block | 15 / 3 / 1 |
| Guard downgrades: citation / numeric | 1 / 2 |
| Judge `FALSE_ABSTAIN` | 15 |
| Top score below `rerank_tau=0.35` | 0 / 19 |
| Expected document in top 6 / top 12 | 14 / 17 |

The conclusion is deliberately narrower than Phase 18's hypothesis: model policy is the
largest observed source of final abstention; the existing low-confidence retry would
trigger on none of these rows; and citation support remains a safety defect but is not
the main false-abstention mechanism.

## Work package 2 — the preregistered experiment

Implement the exact evidence-first block in ADR-0018, version/hash the prompt in the
manifest, and change no other answer-affecting behavior in that commit. Run one full
`qwen3:8b` / `B_hybrid` / guardrails-on candidate cell against the frozen Phase 18
baseline.

The candidate is adopted only if it clears every preregistered quality and safety gate:
at least four fewer deterministic and judge false abstentions; paired judge net wins of
at least four; 10/10 unanswerable abstentions; no injection regression; no citation-hit
or strict-match regression; 80/80 coverage; zero `TOOL_ERR`; green Track-A and CI gates.
Exact wording and thresholds live in ADR-0018 and must not change after the candidate
receipt exists.

If adopted, rerun or explicitly narrow every Phase 18 claim affected by the prompt
change. Old-prompt model/decoding results cannot describe a new-prompt product.

## Work package 3 — harness-generated comparison artifacts

### `reports/variant_matrix.md`

Generate a category-aware A/B/C/D report from committed manifests and answer receipts.
Never manufacture a rectangular comparison where populations differ:

- A and B retrieval evidence may cover all answerable rows while generation evidence
  has a different population.
- D was measured on its 26 aggregation/multi-hop target rows.
- C was measured on six global-summary rows and missed its entity-recall gate.

The report must display each cell's population, model, prompt/decoding version when
known, and manifest id. Missing cells stay blank and are named as unmeasured. The top
narrative must carry Phase 15's 73.3% strict entity recall, 13.6% distinct-entity
precision, fabricated account nodes, underpowered six-row B-vs-C comparison, and
inconclusive context arm without upgrading any of them.

### Failure-taxonomy Pareto sequence

Generate, never hand-edit, at least three comparable historical snapshots from manifest
failure arrays. Each snapshot must disclose its row population and pipeline configuration;
bars from different populations cannot be described as shrinking. If no three snapshots
are actually comparable, produce a coverage table plus the comparable subset and state
that the requested shrinking-bars story is not supported.

### ADR index

There are already 17 numbered ADRs, so the SPEC's “at least eight” count is satisfied.
The artifact should index decisions and statuses; it must not convert waivers, nulls, or
superseded decisions into successes.

## Work package 4 — reader-facing artifacts

- **Demo v2:** show the product's citation trail and honest abstention, the A/B/C/D
  comparison, the six-model null, the decoding null, and the Phase 15 miss. Keep it short
  enough for the internship recipient; do not narrate every implementation detail.
- **Internship report and blog draft:** narrative work follows `CLAUDE.md` and lives in
  the PM-OS workspace, not this compiler/eval repository. Repo-side source tables and
  claims must be generated first; final handoff records their paths/checksums without
  copying stale numbers into two sources of truth.
- **README/app copy:** update only from final generated artifacts, after the abstention
  decision is settled.

## Work package 5 — final truth table and regression

Run `make verify-track-a`, the Phase 19-specific tests, the selected live comparison
cells, and CI. Check CI with `gh run list`; do not infer it. Recheck the synthetic corpus
hash before and after.

The DoD artifact must reconcile, not conceal, known deviations:

- ADR-0003 retired paid hosted tiers, so SPEC §19's three-tier/Kimi/GLM clause is not met.
- ADR-0010 waived Phase 15's measured-and-missed quality gate.
- ADR-0013 waived Phase 17's unattempted machine half; it remains owed before handoff.
- Raw-input replay was deliberately declined in Phase 8 on privacy grounds.
- OCR was exercised on one clean image-only page; no OCR accuracy claim exists.

“Phase 19 closed” may mean its accepted, amended scope is complete. It may not be turned
into “every original SPEC criterion passed.”

## Acceptance

- [x] Entry tests/lint and corpus hash recorded from actual commands.
- [x] Abstention causes and retrieval state captured in a reproducible receipt.
- [x] Experiment and adoption rule committed before the candidate run.
- [ ] Candidate prompt version/hash recorded; one full candidate cell completed.
- [ ] ADR-0018 rule applied without post-result threshold changes; finding written even
      if null or mixed.
- [ ] Any adopted prompt revalidated against affected Phase 18 claims.
- [ ] `reports/variant_matrix.md` harness-generated with population boundaries visible.
- [ ] Pareto sequence or honest non-comparability artifact harness-generated.
- [ ] ADR index generated; ≥8 numbered decisions remain traceable.
- [ ] Demo v2 and PM-OS narrative artifacts completed with current claims.
- [ ] Final DoD truth table names every waiver/deviation above.
- [ ] `make test`, `make lint`, `make verify-track-a`, CI green; corpus hash unchanged.
- [ ] Phase 17 machine/human debt either performed at handoff or still named as debt —
      never silently converted into evidence.

## Boundaries

- No paid APIs. Local Ollama only; `$0.00` means unpriced, not free.
- No user/OCR documents in evals or committed receipts.
- No loosening citation, numeric, injection, or cross-persona guards to improve answer
  rate.
- No second prompt candidate after seeing the first result.
- No hand-edited generated report or chart.
- No change to Phase 15's recorded numbers or Phase 17's waiver status.
- No claim stronger than its manifest population supports.
