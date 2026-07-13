"""Shared retrieval types (SPEC.md 7.2, 9.6, 14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vaultledger.schemas import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    """A retrieved chunk plus a normalized-ish relevance score."""

    chunk: Chunk
    score: float
    rank: int
    source: str


class Retriever(Protocol):
    """Common interface for RAG variants A/B/C/D."""

    variant: str

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        """Return ranked chunks for ``query``."""


__all__ = ["Retriever", "ScoredChunk"]
