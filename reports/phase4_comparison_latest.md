# Phase 4 retrieval comparison

Golden set hash: `b59ee2659a17714c6cff995ef64a8da04cc7d601ca01ba1634d17e296dad551c`
Phase-3 baseline: `phase3_b45ca825de1a`
Phase-4 run: `phase4_e72bb7213548`

| Metric | Dense only | + BM25 / RRF | + rerank | Final delta vs dense |
|---|---:|---:|---:|---:|
| Recall@20 | 0.9587 | 0.9571 | 0.9786 | +0.0199 |
| MRR | 0.4974 | 0.6425 | 0.7856 | +0.2882 |
| Hit rate | 0.9857 | 0.9857 | 0.9857 | +0.0000 |
| Precision@20 | 0.1007 | 0.1021 | 0.1043 | +0.0036 |

All values come from the manifests above; unanswerable examples are excluded from retriever-only metrics.
