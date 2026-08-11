# Phase 15 kickoff — GraphRAG (Variant C)

Status: **in progress** · Opened 2026-08-10

This file is the live phase boundary. Delete it only when every acceptance item
below is discharged and the closing `PROGRESS.md` entry cites the receipts.

## Acceptance ledger

- [x] Lock the engine decision and visualization boundary in ADR-0008: LightRAG
  1.5.x; Graphiti and Microsoft GraphRAG documented alternatives; Obsidian is a
  projection, never the retrieval backend.
- [x] Define the scoreable entity denominator from `entities.json`: 15 people,
  organizations, merchants, and accounts. Addresses remain attributes and
  explanatory relation prose cannot become a hidden recall target.
- [x] Build provider-neutral graph contracts, deterministic entity/relation
  quality scoring, a LightRAG GraphML adapter, and tests.
- [x] Build the generic Obsidian exporter and generate the demo-only ground-truth
  vault: 15 entity notes, 60 document notes, and visible evidence wikilinks. The
  warning inside the vault prevents it being presented as extraction evidence.
- [x] Prove the real embedded SDK/Ollama path on one disposable document. This
  produced 7 nodes/6 edges and a `/private/tmp` receipt: 2 completion calls,
  3 embedding calls, 4,899 input tokens, 802 output tokens, 43.5 seconds, $0.00
  **unpriced** local inference. This is plumbing evidence, not an eval.
- [x] Build the full 60-document index from a clean commit with `make graph-index`.
  The command refuses to overwrite an existing index and writes a versioned
  config/corpus/model/token/latency/cost receipt. Done at `920e7bd`: 60/60
  processed, 45.8 min, receipt `reports/phase15_graph_index_2e50d5948f99.json`.
- [x] Score the full extracted GraphML against the 15-entity denominator. Gate on
  entity recall ≥80%; report precision and the typed-relation exact lower bound.
  **Measured and MISSED: 73.3% recall (11/15), 13.6% precision, 0.0 relation
  recall.** All four misses are accounts extracted under a different surface form;
  ADR-0009's post-hoc, schema-derived last4 rule reads 100% recall / 18.5%
  distinct-entity precision. The earlier node-counted convention is reproduced at
  23.5%; it is not selected because duplicate account nodes should cost precision.
  Both remain secondary diagnostics. See the 2026-08-11 `PROGRESS.md` entries.
- [ ] Wire LightRAG local/global context behind `C_graph`, preserving source chunk
  citations through inserted document IDs/file paths.
- [ ] Run all six `global_summary` rows for C and B on the same model/config from
  a clean commit; write manifests and state the measured margin or null result.
- [ ] Export the **extracted** graph to Obsidian and inspect the vault in graph
  view. Ground-truth projection alone does not close this item.
- [ ] Run the full deterministic suite and relevant live regression gates; append
  the honest close entry to `PROGRESS.md`.

## Smoke finding that must not be extrapolated

The one-document graph contained the two canonical scoreable entities in that
1099 (Cedar Grove Media and David Okafor), plus five form/field concepts. Scoring
it against the full 15-entity corpus denominator yields 13.3% recall and 28.6%
precision, but that population mismatch makes the numbers unsuitable for the
phase AC. The useful finding is qualitative: the local 8B extractor created a
spurious `Form 10909-NEC` node, so full-corpus precision is a real risk to measure.

## Commands

```bash
make install-graph
make graph-vault                 # demo-only ground-truth projection
make graph-index                 # full build; run only from a clean commit
python -m vaultledger.graph score --graphml data/graph/lightrag/graph_chunk_entity_relation.graphml
```
