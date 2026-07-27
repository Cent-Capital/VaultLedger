"""Retrieval variants A/B/C/D behind one Retriever interface + assembly (SPEC 14)."""

from .context import assemble_context
from .hybrid import HybridRetriever, reciprocal_rank_fusion
from .naive import NaiveDenseRetriever
from .rerank import CrossEncoderReranker, Reranker
from .types import Retriever, ScoredChunk

__all__ = [
    "Retriever",
    "ScoredChunk",
    "NaiveDenseRetriever",
    "HybridRetriever",
    "Reranker",
    "CrossEncoderReranker",
    "reciprocal_rank_fusion",
    "assemble_context",
]
