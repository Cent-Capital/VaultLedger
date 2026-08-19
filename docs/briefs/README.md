# Archived phase briefs

These are the **working documents** the build ran on: phase kickoff briefs, review-fix
briefs, close checklists, and two handover notes. They are kept because several are cited
by name in `PROGRESS.md` and in the ADRs, and because they show what each phase was
instructed to do before it did it — which is what makes the preregistered experiments
verifiable rather than merely asserted.

They are **not** current documentation. For that, start at [`docs/README.md`](../README.md).

## Location note — read this if a path looks wrong

Until **2026-08-19** every file in this directory lived at the repository root. The
historical text in `PROGRESS.md` and in the ADRs was deliberately **not** rewritten when
they moved: `PROGRESS.md` is append-only by project rule, and ADRs are amended rather
than edited.

So a reference like ``PHASE16_BUILD_PLAN.md`` in `PROGRESS.md:2186`, or
``PHASE17_CLOSE_CHECKLIST.md`` in ADR-0013, means **the file of that name in this
directory**. Nothing is missing.

Known citations, for convenience:

| Cited file | Cited from |
|---|---|
| `PHASE16_BUILD_PLAN.md` | `PROGRESS.md` (Phase 16 open and close entries) |
| `PHASE17_KICKOFF_BRIEF.md` | ADR-0013 (the machine-half criterion) |
| `PHASE17_CLOSE_CHECKLIST.md` | ADR-0013 (Parts B, C, D — the deferred work) |
| `PHASE17_REVIEW_FIXES_BRIEF.md` | `PHASE17_CLOSE_CHECKLIST.md` |
| `PHASE18_KICKOFF_BRIEF.md` | `PROGRESS.md` (Phase 18 open and close entries), `PM_OS_HANDOVER.md` |
| `ADR0020_IMPLEMENTATION_BRIEF.md` | `PHASE19_KICKOFF_BRIEF.md` |
| `PM_OS_HANDOVER.md` | `PHASE19_KICKOFF_BRIEF.md` |

## What is here

| File | Phase | What it is |
|---|---|---|
| `ROADMAP_RESEQUENCE_BRIEF.md` | pre-16 | The brief behind ADR-0011's re-sequence |
| `PHASE10_CLOSE_BRIEF.md` | 10 | Track-A close criteria |
| `PHASE15_ALIAS_RESCORE_BRIEF.md` | 15 | The task brief behind ADR-0009's account-alias rule |
| `PHASE15_REVIEW_FIXES_BRIEF.md` | 15 | Review fixes before close |
| `PHASE16_BUILD_PLAN.md` | 16 | Implementation order + acceptance-test matrix for live documents |
| `PHASE17_KICKOFF_BRIEF.md` | 17 | Packaging scope, incl. the machine-half gate ADR-0013 later waived |
| `PHASE17_REVIEW_FIXES_BRIEF.md` | 17 | Launcher and reader-facing repairs |
| `PHASE17_CLOSE_CHECKLIST.md` | 17 | Parts A–D; B, C, D remain **owed** (ADR-0013) |
| `PHASE18_KICKOFF_BRIEF.md` | 18 | The ten acceptance criteria for the bake-off and sweep |
| `PHASE18_REVIEW_FIXES_BRIEF.md` | 18 | Pre-experiment corrections |
| `PHASE19_KICKOFF_BRIEF.md` | 19 | Work packages 1–5 for the final phase |
| `PHASE19_CANDIDATE_IMPLEMENTATION_BRIEF.md` | 19 | The ADR-0018 prompt candidate, rejected by ADR-0019 |
| `ADR0020_IMPLEMENTATION_BRIEF.md` | 19 | The support-aware verifier, rejected by ADR-0021 |
| `EMPTY_RESULT_FIX_BRIEF.md` | 19 | The empty-SQL-result contract, rejected by ADR-0022 |
| `ADR0023_RETEST_BRIEF.md` | 19 | The payload-only retest, rejected by ADR-0024 |
| `HANDOFF.md` | early | An early-project handover note; superseded by [`docs/handover.md`](../handover.md) |
| `PM_OS_HANDOVER.md` | 19 | Claim register prepared for the separate PM-OS narrative workspace |

Four of these briefs describe changes that were **built, measured, and then rejected**
(ADR-0019, ADR-0021, ADR-0022, ADR-0024). They are retained deliberately: the rejected
candidate is the evidence that the preregistered rule was applied rather than bent.
