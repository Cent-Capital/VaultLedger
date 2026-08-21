"""Retrieval variants A/B/C/D behind one Retriever interface + assembly (SPEC 14)."""

from .agentic import AgenticRetriever, AgentPlanner, calculate, run_agent_loop, run_readonly_sql
from .context import assemble_context
from .graph import GraphQueryMode, LightRAGRetriever
from .hybrid import HybridRetriever, reciprocal_rank_fusion
from .naive import NaiveDenseRetriever
from .rerank import CrossEncoderReranker, Reranker
from .types import Retriever, ScoredChunk

__all__ = [
    "Retriever",
    "ScoredChunk",
    "NaiveDenseRetriever",
    "HybridRetriever",
    "LightRAGRetriever",
    "GraphQueryMode",
    "Reranker",
    "CrossEncoderReranker",
    "reciprocal_rank_fusion",
    "assemble_context",
    "AgenticRetriever",
    "AgentPlanner",
    "calculate",
    "run_agent_loop",
    "run_readonly_sql",
]
