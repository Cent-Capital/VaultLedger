"""Read LightRAG's local NetworkX GraphML into provider-neutral contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .model import GraphEntity, GraphRelation, GraphSnapshot

_SOURCE_SPLIT_RE = re.compile(r"<SEP>|[|,;]")


def _sources(file_path: Any, source_id: Any) -> tuple[str, ...]:
    # ``file_path`` is the stable VaultLedger doc id passed during insertion.
    # LightRAG's source_id is an internal ``<doc>-chunk-000`` identifier and is
    # only a fallback for older graphs that lack file_path metadata.
    values = (file_path,) if str(file_path or "").strip() else (source_id,)
    found: set[str] = set()
    for value in values:
        for part in _SOURCE_SPLIT_RE.split(str(value or "")):
            item = part.strip()
            if not item:
                continue
            # VaultLedger passes doc ids as LightRAG file_paths.  Native chunk
            # ids such as ``doc#c0`` retain that doc prefix as a fallback.
            item = Path(item).stem.split("#", 1)[0]
            item = re.sub(r"-chunk-\d+$", "", item)
            if item:
                found.add(item)
    return tuple(sorted(found))


def load_lightrag_graphml(path: str | Path) -> GraphSnapshot:
    """Load the default LightRAG GraphML artifact.

    NetworkX stays in the optional ``graph`` extra.  The lazy import keeps the
    base app and deterministic Track-A tests independent from GraphRAG.
    """
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError("Graph support is not installed; install `.[graph]`.") from exc

    graph = nx.read_graphml(Path(path))
    entities = tuple(
        GraphEntity(
            name=str(node),
            kind=str(attrs.get("entity_type", attrs.get("type", "unknown"))).casefold(),
            description=str(attrs.get("description", "")),
            source_doc_ids=_sources(attrs.get("file_path"), attrs.get("source_id")),
        )
        for node, attrs in sorted(graph.nodes(data=True), key=lambda item: str(item[0]))
    )
    relations = tuple(
        GraphRelation(
            subject=str(subject),
            predicate=str(attrs.get("keywords", attrs.get("type", "related_to"))),
            object=str(object_),
            description=str(attrs.get("description", "")),
            evidence_doc_ids=_sources(attrs.get("file_path"), attrs.get("source_id")),
        )
        for subject, object_, attrs in sorted(
            graph.edges(data=True), key=lambda item: (str(item[0]), str(item[1]))
        )
    )
    return GraphSnapshot(
        source=f"lightrag:{Path(path).name}", entities=entities, relations=relations
    )


__all__ = ["load_lightrag_graphml"]
