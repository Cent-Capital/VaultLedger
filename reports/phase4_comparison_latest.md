# Phase 4 retrieval comparison

Golden set hash: `ece0ea370052e5fe97021442dd14cf5533be22d76248568e422a958d9a0e543b`  
Phase-3 baseline: `phase3_b4407e88d3ba`  
Phase-4 run: `phase4_de57151e3ae3`

| Metric | Dense only | + BM25 / RRF | + rerank | Final delta vs dense |
|---|---:|---:|---:|---:|
| Recall@20 | 0.9587 | 0.9571 | 0.9786 | +0.0199 |
| MRR | 0.4974 | 0.6425 | 0.7856 | +0.2882 |
| Hit rate | 0.9857 | 0.9857 | 0.9857 | +0.0000 |
| Precision@20 | 0.1007 | 0.1021 | 0.1043 | +0.0036 |

All values come from the manifests above; unanswerable examples are excluded from retriever-only metrics.
