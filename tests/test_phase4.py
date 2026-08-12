"""Phase 4 deterministic tests: RRF, hybrid dispatch, and comparison reporting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vaultledger.evals.run import _write_comparison
from vaultledger.retrieve import HybridRetriever, ScoredChunk, reciprocal_rank_fusion
from vaultledger.schemas import Chunk, RunManifest


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=f"doc_{chunk_id}",
        text=f"evidence from {chunk_id}",
        page=1,
        char_start=0,
        char_end=10,
    )


class _FakeIndex:
    def __init__(self, hits: list[tuple[str, float]]) -> None:
        self.hits = hits
        self.queries: list[tuple[str, int]] = []

    def query(self, text: str, k: int = 10) -> list[tuple[str, float]]:
        self.queries.append((text, k))
        return self.hits[:k]


class _ReverseReranker:
    model = "fake-cross-encoder"

    def rerank(self, query: str, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        assert query
        return [
            ScoredChunk(hit.chunk, score=0.9 - i / 10, rank=i + 1, source="hybrid+rerank")
            for i, hit in enumerate(reversed(hits))
        ]


def test_reciprocal_rank_fusion_rewards_agreement_and_is_deterministic():
    fused = reciprocal_rank_fusion([["a", "b", "a"], ["b", "c"]], rank_constant=60)
    assert [item_id for item_id, _ in fused] == ["b", "a", "c"]
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1][1] == pytest.approx(1 / 61)
    assert fused[2][1] == pytest.approx(1 / 62)


def test_hybrid_retriever_exposes_rrf_and_reranked_stages():
    chunks = {item_id: _chunk(item_id) for item_id in ("a", "b", "c")}
    dense = _FakeIndex([("a", 0.1), ("b", 0.2)])
    sparse = _FakeIndex([("b", 3.0), ("c", 2.0)])
    retriever = HybridRetriever(
        ".",
        embedder=object(),
        candidate_k=2,
        dense_index=dense,
        sparse_index=sparse,
        chunks=chunks,
        reranker=_ReverseReranker(),
    )

    rrf, final = retriever.retrieve_stages("find evidence", k=3)
    assert [hit.chunk.chunk_id for hit in rrf] == ["b", "a", "c"]
    assert [hit.chunk.chunk_id for hit in final] == ["c", "a", "b"]
    assert all(hit.source == "hybrid_rrf" for hit in rrf)
    assert all(hit.source == "hybrid+rerank" for hit in final)
    assert dense.queries == [("find evidence", 3)]
    assert sparse.queries == [("find evidence", 3)]


def _manifest(run_id: str, variant: str, metrics: dict[str, float]) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        timestamp=datetime.now(UTC).isoformat(),
        git_sha="abc123",
        config_hash="config",
        golden_set_hash="golden",
        seed=42,
        variant=variant,
        model="test-model",
        metrics=metrics,
        total_cost_usd=0.0,
        failures=[],
    )


def test_comparison_report_uses_manifest_values(tmp_path):
    baseline_metrics = {
        "retrieval_recall@20": 0.80,
        "retrieval_mrr": 0.50,
        "retrieval_hit_rate": 0.85,
        "retrieval_precision@20": 0.10,
    }
    current_metrics = {
        "retrieval_recall@20": 0.90,
        "retrieval_mrr": 0.70,
        "retrieval_hit_rate": 0.95,
        "retrieval_precision@20": 0.12,
        **{f"rrf_{key}": value + 0.05 for key, value in baseline_metrics.items()},
    }
    baseline = _manifest("phase3_base", "A_naive", baseline_metrics)
    current = _manifest("phase4_new", "B_hybrid", current_metrics)
    baseline_path = tmp_path / "baseline.json"
    output_path = tmp_path / "comparison.md"
    baseline_path.write_text(baseline.model_dump_json())

    _write_comparison(baseline_path, current, output_path, k=20, reranker_enabled=True)

    report = output_path.read_text()
    assert "phase3_base" in report and "phase4_new" in report
    assert "| Recall@20 | 0.8000 | 0.8500 | 0.9000 | +0.1000 |" in report
    assert "All values come from the manifests" in report
    assert not any(line.endswith(" ") for line in report.splitlines())
