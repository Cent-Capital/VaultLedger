# ADR-0009: Account aliases are schema-derived; precision credits distinct entities

2026-08-11 · Status: **accepted** (owner task brief)

## Context

Phase 15 pre-registered exact canonical entity matching and then missed its recall
gate: 11/15 = 73.3%, below the required 80%. That strict result is valid and stays
the headline record. Inspection afterward showed that people, organizations, and
merchants scored 11/11, while all four structured accounts appeared under other
surface forms.

This ADR is deliberately post-hoc. The alias rule did not exist before the graph
was extracted or before the strict score was known. The extracted GraphML is now
fixed and committed, so a rule could be tuned until it passes. To constrain that
freedom, the rule is derived only from each ground-truth account's structured
`last4` field and is committed with synthetic-fixture tests before any re-score.

## Options

**Leave the miss unqualified.** This preserves the cleanest preregistration story,
but knowingly reports a naming-convention miss as an extraction miss. Rejected:
the strict number must remain, yet a secondary diagnostic can add useful product
information if its post-hoc status and exact rule remain visible.

**Broad fuzzy or semantic entity matching.** Embedding similarity, edit distance,
or an LLM judge could connect many surface forms. Rejected because people,
organizations, and merchants already score perfectly on recall, and broadening
their matcher after observing results creates unjustified scoring latitude.

**A type-scoped structured account rule.** For an expected entity whose kind is
`account`, use only its schema-provided `last4`. Credit an extracted name matching
`\*{2,}\s*<last4>\b` or `ending\s+in\s+<last4>\b`, case-insensitive. The digit
boundary prevents a four-digit account suffix from matching inside a longer
number. This does not alter non-account matching.

For precision, two conventions were considered. Node-counted precision labels
every alias node a true positive, so eight surface nodes for four accounts add
eight numerator credits. Distinct-entity precision gives at most one true-positive
credit per expected account; extra nodes remain in the extracted denominator.

## Decision

Adopt the **type-scoped structured account rule** as a named secondary metric:
`account_last4_masked_or_ending_in`. The ground-truth loader, not the extracted
node name, populates `GraphEntity.account_last4`. The alias table is generated
explicitly from those fields and can be printed or reviewed. Exact canonical
matching remains unchanged for every entity kind.

Use **distinct-entity precision**:
`distinct expected entities matched / unique extracted canonical nodes`. Each
expected account contributes at most one numerator credit. Duplicate aliases cost
precision because they remain separate extracted nodes; they are an entity-
resolution failure, not extra successful extractions. Also emit the node-counted
diagnostic so the earlier 19/81 convention remains reproducible, but do not use it
as the selected alias precision.

The strict result is never replaced. Reports show strict and alias figures side by
side and label the alias result post-hoc.

## Consequences

Account recall now measures whether the extractor found the schema-known account
identifier despite harmless label variation. People, organizations, and merchants
cannot receive fuzzy credit. A ZIP code or paycheck amount that happens to become
a fabricated account node remains a false positive unless it equals a real
ground-truth account's specific last four digits.

Distinct-entity precision will be lower than node-counted precision whenever the
graph fragments one account into several nodes. That is intentional and better
aligned with the product's need for a resolved entity graph. Because the rule is
post-hoc, a passing alias recall does not retroactively turn the original 73.3%
gate into a preregistered pass and does not close Phase 15.

## Evidence

- Strict committed result at `ae8ab71`: recall 11/15 (73.3%), precision 11/81
  (13.6%).
- Full extracted graph fixed at `920e7bd`: 82 raw nodes / 206 edges; scoring
  canonicalizes to 81 unique entity names.
- Re-score intentionally absent from this decision commit. Synthetic fixtures pin
  the account-only scope, digit boundary, and duplicate-penalty convention first.
