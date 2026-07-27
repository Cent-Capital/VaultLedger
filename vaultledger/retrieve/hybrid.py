"""Variant B: dense + BM25 retrieval, RRF fusion, optional reranking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from vaultledger.index.bm25 import Bm25Index
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.index.vector import VectorIndex
from vaultledger.ingest.pipeline import load_chunks
from vaultledger.retrieve.rerank import Reranker
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk


class _DenseIndex(Protocol):
    def query(self, text: str, k: int = 10) -> list[tuple[str, float]]: ...


class _SparseIndex(Protocol):
    def query(self, text: str, k: int = 10) -> list[tuple[str, float]]: ...


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    rank_constant: int = 60,
) -> list[tuple[str, float]]:
    """Fuse ranked ids with ``sum(1 / (rank_constant + rank))``.

    Only rank is used, so incomparable dense distances and BM25 scores never
    need ad-hoc normalization. Duplicate ids inside one ranking count once.
    """
    if rank_constant < 0:
        raise ValueError("rank_constant must be non-negative")
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, item_id in enumerate(ranking, 1):
            if item_id in seen:
                continue
            seen.add(item_id)
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class HybridRetriever:
    """Production retrieval variant with injectable indexes for deterministic tests."""

    variant = "B_hybrid"

    def __init__(
        self,
        index_dir: str | Path,
        embedder: OllamaEmbedder,
        *,
        candidate_k: int = 20,
        rank_constant: int = 60,
        reranker: Reranker | None = None,
        dense_index: _DenseIndex | None = None,
        sparse_index: _SparseIndex | None = None,
        chunks: dict[str, Chunk] | None = None,
    ) -> None:
        if candidate_k < 1:
            raise ValueError("candidate_k must be positive")
        self.index_dir = Path(index_dir)
        self.candidate_k = candidate_k
        self.rank_constant = rank_constant
        self._reranker = reranker
        self._dense = dense_index or VectorIndex(self.index_dir / "chroma", embedder)
        self._sparse = sparse_index or Bm25Index.load(self.index_dir / "bm25.json")
        self._chunks = (
            chunks if chunks is not None else {c.chunk_id: c for c in load_chunks(self.index_dir)}
        )

    @property
    def reranker_enabled(self) -> bool:
        return self._reranker is not None

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        _, final = self.retrieve_stages(query, k=k)
        return final

    def retrieve_stages(
        self, query: str, k: int = 20
    ) -> tuple[list[ScoredChunk], list[ScoredChunk]]:
        """Return (RRF, final) rankings without repeating dense retrieval."""
        if k < 1:
            return [], []
        pool_k = max(k, self.candidate_k)
        dense_hits = self._dense.query(query, k=pool_k)
        sparse_hits = self._sparse.query(query, k=pool_k)
        fused = reciprocal_rank_fusion(
            [[chunk_id for chunk_id, _ in dense_hits], [chunk_id for chunk_id, _ in sparse_hits]],
            rank_constant=self.rank_constant,
        )
        fused_hits = [
            ScoredChunk(
                chunk=self._chunks[chunk_id],
                score=score,
                rank=rank,
                source="hybrid_rrf",
            )
            for rank, (chunk_id, score) in enumerate(fused, 1)
        ]
        hits = fused_hits
        if self._reranker is not None:
            hits = self._reranker.rerank(query, hits)
        return fused_hits[:k], hits[:k]


__all__ = ["HybridRetriever", "reciprocal_rank_fusion"]
