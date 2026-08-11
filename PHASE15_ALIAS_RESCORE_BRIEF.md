# Phase 15 task brief — codify the account alias rule, then re-score

Opened 2026-08-11 · For Codex · Prerequisite reading: the 2026-08-11 `PROGRESS.md`
entry and ADR-0008.

## Why this task exists

`make graph-index` built the full 60-document graph at `920e7bd` and it scored
**73.3% entity recall (11/15), against a ≥80% AC. The gate is missed and is
recorded as missed** in `PROGRESS.md` and commit `ae8ab71`.

The miss is a naming-convention artifact. People, organizations and merchants
scored 11 of 11. All four misses are accounts that *were* extracted, under a
different surface form than `entities.json` uses:

| ground truth | extracted |
|---|---|
| `checking ****4021` | `Account no. ****4021`, `Account: ****4021` |
| `savings ****7788` | `****7788`, `Account ****7788`, `Account no. ****7788` |
| `checking ****3390` | `Account no. ****3390`, `Checking Account Ending in 3390` |
| `checking ****5567` | `Account no. ****5567` |

`quality.py` refuses fuzzy matching by design — its own docstring says crediting
aliases "requires an explicit, reviewable alias table." It behaved as specified.
Your job is to write that table.

## The integrity constraint — read this before writing code

A post-hoc re-score already exists as a **diagnostic only** (100% recall / 23.5%
precision). It is not the phase result, because the rule was written after seeing
the strict number. The extracted GraphML is now committed and fixed, which means
anyone can tune a rule until the number passes. Two safeguards are mandatory:

1. **Derive the rule from the ground-truth schema, not from the extracted names.**
   `entities.json` carries a structured `last4` field per account. The rule keys
   off that field. Do not write a rule by reading the list of extracted node names
   and reverse-engineering something that happens to catch them.
2. **Commit the rule and its tests in a separate commit from the re-score.** The
   diff must show the rule was defined on principle and only then run. Test it
   against synthetic fixtures, not against the real extracted graph.

Do not delete, edit, or soften the strict 73.3% record. Append; never rewrite.

## What to build

**1. `ADR-0009`.** This is a metric-definition change, so it needs an ADR per
`CLAUDE.md`. It must state plainly that the strict rule was specified first,
missed the gate, and that the alias table was introduced afterward in response.
Record the alternative that was rejected: leaving the miss unqualified.

**2. A type-scoped alias rule in `vaultledger/graph/quality.py`.**
- Applies **only** to entities of kind `account`. Do not loosen matching for
  people, organizations or merchants — they already score 11/11, and broadening
  there would inflate the number with no evidence that it is needed.
- An expected account is credited iff an extracted node name contains that
  account's specific `last4`, anchored so it cannot match a substring of a longer
  number. The reference rule used for the diagnostic was: node name matches
  `\*{2,}\s*<last4>\b` or `ending\s+in\s+<last4>\b`, case-insensitive.
- Keep the alias table explicit and inspectable, per the existing docstring's
  own standard.

**3. Two decisions you must make explicitly and document — do not let them fall
out of the implementation by accident:**

- **Precision numerator convention.** Eight extracted nodes map to four expected
  accounts. Does precision count *credited nodes* (giving 19/81 = 23.5%) or
  *distinct expected entities matched* (giving 15/81 = 18.5%)? Both are
  defensible; pick one, state it, and apply it consistently.
- **Whether duplicates should cost precision.** `****7788`, `Account ****7788`
  and `Account no. ****7788` are three nodes for one real account. That is an
  entity-resolution failure. Crediting all three arguably rewards the model for
  fragmenting an entity. Consider whether the rule should credit one node per
  expected account and treat the rest as unmatched.

**4. Re-score and report both numbers.** Strict and alias figures side by side,
with the alias rule named. Append a `PROGRESS.md` entry; do not edit the existing
one.

## Reproduction targets

Your implementation should reproduce these against the committed GraphML
(`data/graph/lightrag/graph_chunk_entity_relation.graphml`, 82 nodes / 206 edges):

```
strict (already committed):  recall 11/15 = 73.3%  | precision 11/81 = 13.6%
alias, node-counted:         recall 15/15 = 100.0% | precision 19/81 = 23.5%
```

If your numbers differ, your rule differs from the diagnostic — investigate before
reporting, and say which is right.

## Do not touch

- The built GraphML or `reports/phase15_graph_index_2e50d5948f99.json`.
- The 15-entity denominator or ADR-0008's population definition.
- The relation metric. Relation recall 0.0 is a **vocabulary** artifact (typed
  predicates vs LightRAG keyword bags), a separate problem from account aliasing.
  Fixing it needs a predicate mapping and is out of scope here.

## Acceptance

- [ ] ADR-0009 accepted, stating the post-hoc origin of the rule honestly.
- [ ] Alias rule + tests committed **before** the re-score commit.
- [ ] `make test` and `make lint` green; new tests cover the account rule and
  prove non-account matching is unchanged.
- [ ] Both strict and alias numbers reported, with the precision convention named.
- [ ] `PROGRESS.md` appended, strict 73.3% record left intact.

## What this does NOT do

**Passing recall does not close Phase 15.** Precision is 13.6%–23.5% either way,
and the extractor fabricates account identifiers from unrelated numbers — a payer
ZIP code became `Checking Account Ending in 07302`, and a net pay of $2,525.39
became `...Ending in 2525`. Three acceptance items also remain unbuilt: `C_graph`
local/global retrieval with source-chunk citations, same-model B-vs-C scoring on
the six `global_summary` rows, and an extracted-graph Obsidian export (no CLI path
exists — `export-ground-truth` is currently the only export subcommand).
