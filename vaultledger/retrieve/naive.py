"""Variant A: naive dense retrieval over Chroma (SPEC.md 14.1)."""

from __future__ import annotations

from pathlib import Path

from vaultledger.index.embed import OllamaEmbedder
from vaultledger.index.vector import VectorIndex
from vaultledger.ingest.pipeline import load_chunks
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Variant


class NaiveDenseRetriever:
    """Dense top-k only; kept as the permanent baseline."""

    variant: Variant = "A_naive"

    def __init__(self, index_dir: str | Path, embedder: OllamaEmbedder) -> None:
        self.index_dir = Path(index_dir)
        self._vector = VectorIndex(self.index_dir / "chroma", embedder)
        self._chunks = {c.chunk_id: c for c in load_chunks(self.index_dir)}

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        hits = self._vector.query(query, k=k)
        scored: list[ScoredChunk] = []
        for rank, (chunk_id, distance) in enumerate(hits, 1):
            chunk = self._chunks[chunk_id]
            # Chroma returns distance where lower is better. Convert to a bounded
            # score for display/eval ordering without claiming calibrated confidence.
            score = 1.0 / (1.0 + max(float(distance), 0.0))
            scored.append(ScoredChunk(chunk=chunk, score=score, rank=rank, source="dense"))
        return scored


__all__ = ["NaiveDenseRetriever"]
