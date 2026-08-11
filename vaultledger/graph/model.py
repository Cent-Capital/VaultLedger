"""Provider-neutral graph contracts for Phase 15.

LightRAG owns extraction and retrieval, but it must not own the evaluation
denominator or the Obsidian projection.  These small immutable contracts keep
both consumers independent from LightRAG's storage schema and version churn.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphEntity:
    name: str
    kind: str = "unknown"
    description: str = ""
    source_doc_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GraphRelation:
    subject: str
    predicate: str
    object: str
    description: str = ""
    evidence_doc_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GraphSnapshot:
    """One graph plus an honest label for where its nodes came from."""

    source: str
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]


__all__ = ["GraphEntity", "GraphRelation", "GraphSnapshot"]
