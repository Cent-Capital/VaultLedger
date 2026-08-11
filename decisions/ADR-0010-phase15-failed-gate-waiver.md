# ADR-0010: Phase 15 receives a one-phase failed-gate waiver

2026-08-11 · Status: **accepted** (owner review brief)

## Context

The repository's phase discipline says not to begin a phase until the preceding
phase's SPEC acceptance criteria pass. Phase 15's pre-registered strict entity
recall was 11/15 = 73.3%, below the required 80% by 6.7 percentage points and one
matched entity. Closing Phase 15 and naming Phase 16 as next therefore requires an
explicit waiver; an implicit exception would turn an evidence-preserving decision
into an apparent process violation.

The miss is not erased. A post-hoc, schema-derived account diagnostic finds all
four missing accounts and raises recall to 15/15, but its 18.5% distinct-entity
precision remains poor and the extracted graph contains fabricated account-like
nodes. That diagnostic explains the strict miss without retroactively passing the
pre-registered gate.

## Options

**Keep Phase 15 open until strict recall passes.** This would preserve the phase
rule literally, but it would encourage tuning extraction or matching against an
already observed graph. A later pass would be less credible and would postpone the
more important precision and fabrication findings.

**Redefine the gate around the account-alias result.** Rejected. ADR-0009 records
that rule as post-hoc, so promoting it to the original acceptance metric would
rewrite the experiment after seeing the outcome.

**Close with a narrow, explicit waiver.** The implementation, full-corpus index,
cost receipt, strict and secondary scoring, B-vs-C evaluation, and real Obsidian
inspection are complete. Preserve the failed result and allow Phase 16 to begin
without claiming the gate passed.

## Decision

Grant the third option for **Phase 15 only**. Phase 15 closes as a completed
implementation and evaluation milestone, not as an all-green acceptance result.
The strict 73.3% recall remains the headline and the ≥80% AC remains failed.

Revisit graph extraction quality before Variant C can be promoted or before any
production claim. A revisit requires a new extraction run and a matching/entity-
resolution metric fixed before that graph is inspected. The successor result must
meet its pre-registered recall threshold while materially improving precision and
auditing fabricated account identifiers; a larger capable local extractor and an
explicit predicate mapping are reasonable inputs, not automatic passes.

This waiver does not weaken the phase rule generally and does not authorize closing
Phase 16 or any later phase on a failed gate. Any future exception needs its own
recorded decision and evidence.

## Consequences

Phase 16 may start without pretending Phase 15 passed. Portfolio reporting must
carry the strict miss, the post-hoc qualifier, and the poor precision result. The
waiver also creates a clear promotion boundary: Variant C remains experimental
until a new pre-registered run discharges the quality concerns.

## Evidence

- Strict score: 11/15 = 73.3% recall and 11/81 = 13.6% precision.
- ADR-0009 secondary score: 15/15 = 100% recall and 15/81 = 18.5% selected
  precision, explicitly post-hoc.
- Full graph receipt: `reports/phase15_graph_index_2e50d5948f99.json`.
- Phase 15 close and limitations: `PROGRESS.md`.
