# ADR-0008: LightRAG extraction and retrieval; Obsidian as a projection

2026-08-10 · Status: **accepted** (the engine default and vault boundary are explicit
Phase-15 requirements in SPEC §14.3)

## Context

Phase 15 must extract an entity/relation graph over 60 local financial documents,
score entity recall against the committed synthetic ground truth, expose local and
global graph retrieval as Variant C, preserve source-document citations, and make
the graph visible in Obsidian. The owner constraint in ADR-0003 retires all paid
APIs: the spec's T2 index-time call falls back to the largest local model that
fits, with the quality loss and zero-dollar-but-unpriced compute reported honestly.

The installed inventory was inspected rather than inferred from model tags.
`qwen3:8b` declares **8.2B parameters**, a 40,960-token context, and Q4_K_M
quantization. `gemma4:e2b` occupies more disk but declares only 5.1B parameters.
The index extractor is therefore `ollama/qwen3:8b`. This is much smaller than
LightRAG's current ≥32B recommendation; the ≥80% recall AC remains a hypothesis,
not a promised result.

## Options

**LightRAG (HKUDS).** It provides LLM entity/relation extraction, a persisted
NetworkX graph by default, and entity-centric `local` plus relationship-centric
`global` query modes. Its embedded SDK is small enough to inspect and run against
Ollama, and its `ids`/`file_paths` insertion metadata provides a citation seam.
The cost is a fast-moving API and an extraction pipeline designed around models
larger than this machine's local lineup.

**Graphiti (getzep).** Its bi-temporal edges and incremental memory are valuable
when the product's headline is change over time. VaultLedger's current questions
are a static, regenerated 60-document corpus. Adopting Graphiti would add a graph
database and temporal semantics that the golden set does not evaluate.

**Microsoft GraphRAG.** Community detection and hierarchical reports are the
strongest fit for corpus-level thematic summaries. They also add the heaviest
index-time generation pipeline. At this corpus size and under a no-paid-API
constraint, that machinery is disproportionate, and its extra calls amplify the
known local-model quality constraint.

**Ground-truth graph only.** This is the spec's pre-agreed cut line: a ten-document
LightRAG spike plus an Obsidian projection of ground truth. It produces an honest
visual demo but cannot be called Variant C and cannot generate extraction metrics.

## Decision

Use **LightRAG 1.5.x** through a narrow adapter, with local NetworkX storage and
Ollama. Keep provider-neutral `GraphSnapshot`, scoring, and export contracts in
VaultLedger so a LightRAG upgrade cannot change the evaluation denominator. The
scoreable entity population is defined as the graph types named by SPEC §14.3:
people, organizations, recurring merchants, and accounts. Addresses remain
attributes. A descriptive object on the `shared_address` ground-truth relation is
not allowed to silently become an entity-recall target.

Use **Obsidian only as a generated visualization projection**: one note per entity
and document, with evidence relationships as wikilinks. Retrieval remains
LightRAG. A ground-truth export carries a warning in the vault itself that it is
demo data and cannot support a recall claim.

The embedded SDK is pinned to `lightrag-hku>=1.5.6,<1.6`. LightRAG's official SDK
guide says the core API is intended for embedded/research use and may change; the
minor-line cap makes that instability explicit. Query and indexing decoding must
disable Qwen thinking, preserving ADR-0007's generator-parity rule.

## Consequences

Graph quality has a stable, deterministic denominator and can be unit-tested
without LightRAG or Ollama. The vault can be generated immediately from either
ground truth or a real extracted graph, and its provenance label travels inside
the artifact. Graphiti's temporal value and Microsoft GraphRAG's community reports
remain documented alternatives instead of unused dependencies.

The risk is concentrated where it belongs: local extraction quality. If 8B misses
the 80% recall threshold, the phase reports the miss. It may use the ten-document
spike cut line, but it may never score the ground-truth projection as extracted
output or call it Variant C.

## Evidence

- Official LightRAG 1.5.6 documentation inspected 2026-08-10: default
  `NetworkXStorage`; `local` and `global` `QueryParam` modes; insertion supports
  `ids` and `file_paths`; SDK called version-sensitive by its maintainers.
- Local `ollama show` receipts inspected 2026-08-10: `qwen3:8b` = 8.2B parameters;
  `gemma4:e2b` = 5.1B parameters.
- No LightRAG index, extraction score, Variant-C eval, or indexing-cost receipt
  exists at ADR acceptance time. Those remain Phase-15 acceptance work.
