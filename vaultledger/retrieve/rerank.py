"""Optional cross-encoder reranking for retrieval Variant B (SPEC 14.2)."""

from __future__ import annotations

import math
from typing import Protocol

from vaultledger.retrieve.types import ScoredChunk


class Reranker(Protocol):
    """A query-aware second-stage ranker over an already bounded candidate set."""

    model: str

    def rerank(self, query: str, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        """Return every input hit ordered by cross-encoder relevance."""


class CrossEncoderReranker:
    """Lazy ``sentence-transformers`` wrapper around BGE's cross-encoder."""

    def __init__(self, model: str = "BAAI/bge-reranker-base", batch_size: int = 16) -> None:
        self.model = model
        self.batch_size = batch_size
        self._cross_encoder = None

    def _load(self):
        if self._cross_encoder is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "reranking is enabled but sentence-transformers is not installed; "
                    "run `pip install -e '.[rerank]'` or pass --no-reranker"
                ) from exc
            self._cross_encoder = CrossEncoder(self.model, num_labels=1)
        return self._cross_encoder

    def rerank(self, query: str, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        if not hits:
            return []
        pairs = [(query, hit.chunk.text) for hit in hits]
        raw_scores = self._load().predict(pairs, batch_size=self.batch_size)
        scored = []
        for hit, raw in zip(hits, raw_scores, strict=True):
            # BGE emits an unbounded relevance logit. Logistic conversion makes it
            # safe for Answer.confidence without claiming calibration.
            logit = float(raw)
            if logit >= 0:
                score = 1.0 / (1.0 + math.exp(-logit))
            else:
                exp_logit = math.exp(logit)
                score = exp_logit / (1.0 + exp_logit)
            scored.append((hit, score))
        scored.sort(key=lambda item: (-item[1], item[0].chunk.chunk_id))
        return [
            ScoredChunk(
                chunk=hit.chunk,
                score=score,
                rank=rank,
                source="hybrid+rerank",
            )
            for rank, (hit, score) in enumerate(scored, 1)
        ]


__all__ = ["CrossEncoderReranker", "Reranker"]
