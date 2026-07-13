"""Retrieval variants A/B/C/D behind one Retriever interface + assembly (SPEC 14)."""

from .context import assemble_context
from .naive import NaiveDenseRetriever
from .types import Retriever, ScoredChunk

__all__ = ["Retriever", "ScoredChunk", "NaiveDenseRetriever", "assemble_context"]
