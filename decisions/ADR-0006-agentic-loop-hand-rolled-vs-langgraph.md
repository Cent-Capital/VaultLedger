# ADR-0006: Variant D's agent loop — hand-rolled, not LangGraph

2026-08-05 · Status: **accepted** (owner, 2026-08-05, with the `AgentStep` amendment
below)

## Context

Phase 14 builds variant D, agentic RAG. SPEC §14.4 specifies four tools —
`retrieve` (delegating to variant B), `calculator` (safe arithmetic),
`sql` (read-only SQLite over the typed records, SELECT-only with a table
allowlist), and `finish` — driven by a plan → act → observe loop hard-capped at
**6 steps** (`loops.agent_steps_max`) plus a per-query token budget, with every
step logged as an `AgentStep` and budget exhaustion producing an honest abstention
carrying the partial trace.

The contracts already exist. `AgentStep` is in `schemas.py` with a
`Literal["retrieve","calculator","sql","finish"]` tool field, `Answer.agent_steps`
is already declared "variant D only", `Variant` already includes `D_agentic`, and
the SQLite typed-record store built in Phase 2 is already read by the Phase 13
numeric verifier. SPEC §15.2 bans `while True`; every loop budget lives in
`config.yaml`.

SPEC names this ADR and pre-indicates the answer — "build it yourself; LangGraph
documented as the alternative in an ADR". The decision still has to be argued
rather than asserted, because the reasoning is what an interview probes.

**Two findings from the pre-Phase-14 review change what Phase 14 must do first,
independent of the loop choice.** They are recorded in *Prerequisites* below.

## Options

**A. Hand-rolled bounded loop.** A `for step in range(agent_steps_max)` over a
small dispatch table, with the scratchpad as an explicit list of `AgentStep`
records. Roughly 150 lines. No new dependency. The loop, its budgets, and its exit
conditions are readable in one screen and testable with a scripted fake generator
— the pattern Phase 5's repair loop already uses. The cost is that everything —
retries, partial-failure handling, streaming — is yours to write.

**B. LangGraph.** A durable graph runtime: typed state, conditional edges,
checkpointing, resumability, streaming, and a visualiser. Genuinely good at
long-running multi-actor workflows. The costs here are specific rather than
generic. It owns the control flow, which is the third time this repo has faced
that tradeoff — ADR-0002 rejected `instructor` and ADR-0005 rejected Guardrails-AI
for the same reason, and an agent loop nested inside the Phase 5 repair loop and
the Phase 12 escalation loop is where competing control flows would actually
collide. Its budget model is also not the one SPEC specifies: `recursion_limit`
caps graph depth, not the 6 tool-steps-plus-token-budget this project measures, so
the budget that matters would end up enforced outside the framework anyway.

**C. A lighter agent library** (`pydantic-ai`, `smolagents`, LlamaIndex agents).
Less machinery than LangGraph, and `pydantic-ai` would compose with the existing
Pydantic contracts. Still a dependency that owns the loop, and still ships a
retry/validation layer that duplicates Phase 5. The gain over A is small when the
loop is 6 bounded steps over 4 local tools.

## Decision

**Accepted: A — hand-rolled bounded loop.** Owner decision 2026-08-05, with the
`AgentStep` amendment recorded under *Design commitments*.

The decisive argument is not engineering taste, it is that **the loop is the
deliverable**. SPEC G11 is "loop & harness engineering: every loop in the system
has explicit budgets and exit conditions"; §15 makes the loop inventory a
cross-cutting Track B/C/D artifact. Delegating the loop to a framework would
outsource precisely the competency Phase 14 exists to demonstrate, and the
portfolio artifact would become "I configured LangGraph" rather than "I can reason
about termination, budgets, and partial failure." A 6-step bounded loop over four
local tools is small enough that the framework's benefits — durability,
resumability, multi-actor orchestration — buy nothing this corpus needs.

LangGraph is documented here as the alternative, per SPEC, and is the right answer
at a different scale: many actors, long-running workflows, or human-in-the-loop
resumption. None apply to a single-turn question answered in under six steps
against a 60-document local corpus.

**Design commitments:**
- `for` over a fixed budget from `config.yaml`. No `while True` (§15.2 CI ban).
- Every step appends an `AgentStep` before dispatch, so an exhausted or crashed
  run still has a trace.
- Exhaustion returns the **safest viable answer** with the partial trace, never a
  guess — the same abstention contract Phase 5 established.
- The `sql` tool is SELECT-only with a table allowlist, parameterised, and given
  no write path. It is a genuine attack surface: SPEC §14.4 has SQL results
  carrying `doc_id` provenance so citations survive the tool hop, which means
  untrusted document text can influence a query path. **Phase 7's injection suite
  must be re-run with variant D live**, and the Phase 13 guards must be active
  during that run — the Phase 13 review showed the eval path can silently run
  without them.
- Variant D runs behind the same `Retriever` interface, so the matrix scores it
  without special-casing.
- **`AgentStep` gains an explicit failure representation** (owner amendment,
  2026-08-05). SPEC §8 fixes the contract at five fields — `step`, `tool`, `input`,
  `output_summary`, `tokens_used` — none of which can say that a tool *raised*.
  This ADR commits to hand-written partial-failure handling, so without a
  structural field the only place a failure could go is prose inside
  `output_summary`, which is unqueryable and indistinguishable from a tool that
  succeeded and returned bad news. The field is added before Phase 14 writes any
  receipt against the contract, so no committed receipt needs migrating. This is a
  **deviation from SPEC §8** and is recorded in SPEC §0's ACTIVE DEVIATIONS banner.

  *Implemented 2026-08-06 in Phase 14's opening change.* The field landed before
  any Phase 14 artifact was committed, so no historical receipt required migration.

## Prerequisites — Phase 14 cannot state its AC without these

Phase 14's AC is *"numeric exact-match on multi_hop/aggregation improves by a
stated, measured margin vs B."* Two gaps blocked it, both found in review. **Both
were closed on 2026-08-05, before any Phase 14 code**, as reporting changes only —
no inference was re-run.

1. **~~No per-category metrics exist.~~ Closed.** `category_metrics()` in
   `evals/matrix.py` emits `<metric>__<category>` keys into every manifest and
   `write_matrix_report` renders a per-category table. Denominators come from the
   golden set rather than the completed rows, so a row that failed to produce an
   `Answer` counts as a miss in its category instead of shrinking the population.
2. **~~No "numeric exact-match" metric exists.~~ Closed — the metric was added.
   The AC was *not* restated.** `numeric_exact_match()` parses quantities on both
   sides and compares them within `thresholds.numeric_epsilon`, so `$1,234.50`
   against `1234.5` scores as a match where `strict_answer_match` scores a miss.
   The two names stay distinct in code, in the manifest keys, and in the generated
   report. Its limits are stated where it is defined: it is a presence test, its
   bias runs toward *over*-crediting (the opposite direction from
   `strict_answer_match`), and it is not a judge verdict. Rows whose reference
   carries no quantity — including every `unanswerable` row — are held out of the
   denominator rather than scored as failures, so the metric has its own `n`.

**Comparability is enforced in code, not by convention.** `score_answer()` is the
single per-row scorer; the live matrix and the offline `rescore` path both call it,
so the variant-B baseline below and a future variant-D cell cannot be scored by
drifting versions of the same metric.

**Variant B baseline, computed offline from the committed guards-on receipts**
(the number Phase 14 must beat). Regenerate with
`python -m vaultledger.evals rescore --answers <receipts> --report
reports/phase14_baseline_by_category.md`; the full eight-category table is in that
file.

| category | n | strict `4b` | strict `8b` | numeric n | numeric `4b` | numeric `8b` |
|---|---:|---:|---:|---:|---:|---:|
| `aggregation` | 14 | 28.6% | 14.3% | 12 | 33.3% | 16.7% |
| `multi_hop` | 12 | 16.7% | **0.0%** | 12 | 16.7% | **0.0%** |

The strict columns were hand-computed during the pre-Phase-14 review and are
reproduced here by the shipped scorer, which is why they are stated as measured
rather than estimated. The numeric columns are new and were never available before.

The headroom is large and the floor is honest: 8B answers **zero of twelve**
multi-hop questions on both scorers. If variant D cannot beat that, the null result
is worth publishing.

**Which number is the AC's baseline:** `numeric_exact_match_rate__multi_hop` and
`numeric_exact_match_rate__aggregation`, against the same model variant D runs on.
Comparing variant D's numeric rate to variant B's *strict* rate would be a
scorer-swap dressed as an improvement.

## Consequences

**Easier.** No dependency, no version churn, no framework upgrade breaking the
loop. The loop is inspectable and unit-testable with a scripted generator, matching
the Phase 5 pattern already proven here. Budgets stay in `config.yaml` where every
other budget lives, so the loop inventory §15 asks for stays coherent.

**Harder.** Retries, partial-tool-failure handling, and any future streaming are
all hand-written. There is no free graph visualiser — the step trace in the UI has
to serve that role. If the agent later needs multi-actor orchestration or
resumable long-running runs, this decision must be revisited rather than extended.

**Risk accepted.** The `sql` tool is the largest new attack surface in the project.
SELECT-only and an allowlist are necessary but not sufficient evidence; only a
live injection run with variant D active demonstrates it.

*Discharged 2026-08-10.* Phase 7's suite was re-run with variant D live and all
Phase 13 guards active (`phase14_safety_*`, `guardrails_enabled: 1.0`). The agent
**resisted** the embedded instruction (`injection_resisted: 1.0`) and then
over-refused rather than answering (`injection_answered_correctly: 0.0`). The tool
itself held under probes beyond the test suite — subquery, `UNION`, CTE and
`sqlite_master` exfiltration all blocked by the SQLite authorizer's default-DENY.
Two findings the run did surface are recorded in `PROGRESS.md` and left unfixed:
variant D scores 9/10 on abstention against B's 10/10, and the `sql` tool fails
39–47% of the calls the planner makes to it. Getting this evidence at all required
ADR-0007, because the safety path was decoding differently from the eval gateway.

**Revisit when** the agent needs more than one actor, runs long enough to need
resumption, or the loop exceeds roughly 300 lines — at which point a framework is
carrying real weight rather than ceremony.

## Evidence

- `AgentStep`, `Answer.agent_steps`, and `Variant["D_agentic"]` already exist in
  `schemas.py`, inspected 2026-08-05.
- `loops.agent_steps_max: 6` and `loops.escalations_max: 2` are in `config.yaml`.
- SPEC §8 defines `AgentStep` with exactly five fields and no failure channel;
  `schemas.py:74` matches it field-for-field. Inspected 2026-08-05, which is why
  the amendment above is classed as a deviation rather than a clarification.
- Per-category variant-B baselines above computed from committed receipts
  `phase11_ollama_qwen3_4b_b_hybrid_35d35e2fb62f_answers.json` and
  `..._8b_..._eea876388398_answers.json` (guards-on arm, n=80, failed rows scored
  as misses).
- No matrix manifest contains a category-scoped metric; verified by inspecting the
  metric keys of `..._eea876388398.json`.
- **Not measured:** no agent loop exists yet. Every claim about hand-rolled versus
  framework maintainability is a reasoned estimate, not a measured result. The
  claim that variant D will beat B on multi-hop is a hypothesis Phase 14 tests, not
  a prediction this ADR is entitled to make.
