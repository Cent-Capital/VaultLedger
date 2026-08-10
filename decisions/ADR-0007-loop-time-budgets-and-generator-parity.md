# ADR-0007: Bounded loops need a wall-clock budget, and every generator must decode like the eval gateway

2026-08-10 · Status: **accepted** (owner, 2026-08-10)

## Context

Two defects found while closing Phase 14. They are unrelated in mechanism and
identical in consequence: **the harness measured something other than the system.**

**1. The agent loop had no wall-clock budget.** SPEC G11 requires every loop to
carry explicit budgets and exit conditions, and ADR-0006 delivered two: a step
budget (`loops.agent_steps_max`) and a token budget (`loops.agent_tokens_max`).
Neither bounds elapsed time. `OllamaGenerator` uses a 180-second request timeout
and raises `GenerationError`, which subclasses `RuntimeError` — the exact type the
loop's planner handler catches. So a stalled generator produced: 180s block →
caught → recorded as a planner error → step consumed → next step → 180s block. Six
steps is 18 minutes for one question; the 11-row safety suite is over three hours.
Observed directly: a `faulthandler` dump showed two identical stacks 90 seconds
apart, blocked in `socket.readinto` under `run_agent_loop`.

Neither existing budget advances during a stall. A stalled call returns no tokens,
so the token counter is frozen; steps only advance once per timeout. **The budgets
that existed could not bound the failure they were supposed to bound.**

**2. `OllamaGenerator` never disabled Qwen 3's thinking; the eval gateway did.**
`LiteLLMGenerator` has passed `think=False` since Phase 11, with a comment
explaining that thinking tokens are charged against the output budget and can
consume it entirely. `OllamaGenerator` — used by the Streamlit app and by the
Phase 7/14 safety runner — never got the same treatment.

Measured on `qwen3:8b` at `num_predict=64`:

| | `response` | `done_reason` |
|---|---|---|
| thinking on (product path) | `""` | `length` |
| thinking off (gateway path) | `{"tool": "finish"}` | `stop` |

Variant D's planner was therefore handed empty strings, failed to parse them, and
recorded planner errors until its step budget was gone. **The matrix scored a
system that never had this problem; the safety runner scored one that always did.**
This is the third instance of the same family — Phase 13 found the eval path
running with `guardrail_toggles=None`, and Phase 11 found the egress badge
asserting rather than deriving.

## Options

**A. Fix both; add a third budget; make parity a rule.** Time budget in
`config.yaml` beside the other two, transport failures labelled apart from planner
failures, `think=False` on every generator, and a test pinning parity.

**B. Fix only the thinking bug.** It is the proximate cause of the stall, and
without it the loop rarely runs long. Cheaper, and leaves the loop unbounded in
time — the next slow dependency reproduces the outage. Rejected: a budget that
only holds while nothing is slow is not a budget.

**C. Lower the HTTP timeout instead of adding a loop budget.** Bounds each call
but not the loop: six steps at any per-call timeout still multiply. It also
conflates "this request is slow" with "this query has taken too long", which are
different decisions. Rejected as insufficient alone, though the 180s timeout is
worth revisiting separately.

## Decision

**Accepted: A.**

- **`loops.agent_seconds_max: 300`** joins the step and token budgets in
  `config.yaml`. Checked before each planner call and after each dispatch, so the
  loop exits on a stall rather than at `steps × timeout`. Sized above the observed
  worst case for six legitimate steps of a slow local model, so it fires on stalls
  and not on slowness.
- **Transport failures are counted and labelled separately** from planner
  failures (`transport_error:` vs `planner_error:` in `AgentStep.failure`, plus
  `AgentLoopResult.transport_errors`). An unreachable generator is an
  infrastructure fact. Recording it as "the model produced a bad action"
  attributes an outage to model quality — which is exactly how Phase 14's stall
  was first misread.
- **Every generator the product uses must match the eval gateway's decoding
  settings.** `OllamaGenerator` now sends `think=False`. A test asserts it, so the
  two paths cannot silently diverge again.

## Consequences

**Easier.** A stalled dependency now costs one query its time budget instead of
hours of harness time, and the abstention says which budget was hit and whether
transport was involved. The product path and the eval path decode identically, so
a Variant-D number from the app and one from the matrix mean the same thing.

**Harder.** There is now a third budget to keep coherent in the SPEC §15 loop
inventory, and a fourth number that can be tuned wrong. A time budget is also
machine-dependent in a way step and token budgets are not: the same 300 seconds is
generous on this laptop and might not be elsewhere. It is a stall detector, not a
performance target, and should not be tightened to make runs faster.

**What this invalidates.** The committed Phase 14 matrix manifests are
**unaffected** — they ran through `LiteLLMGenerator`, which already had
`think=False`, and carry zero transport failures (verified by inspecting every
step's failure field in both receipts). The pre-fix Variant-D safety run is
**discarded**: it measured the thinking-on path and is not evidence about the
system that ships. Phase 7's committed `B_hybrid` baseline also predates the
parity fix and should be read as measuring the thinking-on path until re-run.

**Revisit when** a generator legitimately needs more than the time budget — a
larger local model, or a machine slower than this one — at which point the budget
moves, but never below the honest worst case for a healthy run.

## Evidence

- `faulthandler` stacks, 90s apart, identical, blocked in `socket.readinto` under
  `run_agent_loop` → `ollama.py:_generate`. Captured 2026-08-07.
- `GenerationError.__mro__` includes `RuntimeError`; the loop's handler catches
  `(ValidationError, ValueError, TypeError, RuntimeError)`. Verified by inspection.
- The `think` on/off table above: measured directly against the local Ollama
  daemon on `qwen3:8b`, 2026-08-10.
- Zero `transport_error` rows in both committed Phase 14 matrix receipts, which is
  why the acceptance margins stand unchanged.
- **Not measured:** whether 300 seconds is the right number on any machine other
  than this one. It is a reasoned bound from observed healthy-run durations, not a
  measured optimum.
