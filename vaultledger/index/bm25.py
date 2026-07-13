"""Lexical index: BM25 over the same chunks as the vector index (SPEC.md FR3).

``rank_bm25`` holds the index in memory; what persists is the tokenized
corpus + chunk ids as JSON, from which the index rebuilds in milliseconds.
The same ``chunk_id`` keys this index, the Chroma collection, and (later) the
graph — that shared key is what lets RRF fuse result lists in Phase 4.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from vaultledger.schemas import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens; '$4,207.55' -> ['4', '207', '55']."""
    return _TOKEN.findall(text.lower())


class Bm25Index:
    def __init__(self, chunk_ids: list[str], tokenized: list[list[str]]) -> None:
        self.chunk_ids = chunk_ids
        self._tokenized = tokenized
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    @classmethod
    def build(cls, chunks: list[Chunk]) -> Bm25Index:
        return cls([c.chunk_id for c in chunks], [tokenize(c.text) for c in chunks])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"chunk_ids": self.chunk_ids, "tokenized": self._tokenized})
        )

    @classmethod
    def load(cls, path: str | Path) -> Bm25Index:
        data = json.loads(Path(path).read_text())
        return cls(data["chunk_ids"], data["tokenized"])

    def query(self, text: str, k: int = 10) -> list[tuple[str, float]]:
        """Lexical top-k: returns (chunk_id, score) pairs, best first."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(text))
        ranked = sorted(zip(self.chunk_ids, scores, strict=True), key=lambda p: -p[1])
        return ranked[:k]


__all__ = ["Bm25Index", "tokenize"]
