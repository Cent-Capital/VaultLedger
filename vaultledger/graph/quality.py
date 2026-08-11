"""Deterministic graph extraction metrics against ``entities.json``."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .model import GraphSnapshot

_SPACE_RE = re.compile(r"\s+")
_QUOTE_RE = re.compile(r"^[\"']+|[\"']+$")


def canonical_name(value: str) -> str:
    """Normalize harmless provider formatting without doing fuzzy matching.

    Case, Unicode width, surrounding quotes, underscores, and repeated spaces
    are representation differences.  Abbreviations and semantic aliases are
    not guessed; crediting those requires an explicit, reviewable alias table.
    """
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _QUOTE_RE.sub("", normalized).replace("_", " ")
    return _SPACE_RE.sub(" ", normalized).casefold()


@dataclass(frozen=True)
class GraphQuality:
    expected_entities: int
    extracted_entities: int
    matched_entities: int
    entity_recall: float
    entity_precision: float
    expected_relations: int
    extracted_relations: int
    matched_relations: int
    relation_recall: float
    relation_precision: float

    def as_metrics(self) -> dict[str, float]:
        return {
            "graph_expected_entities": float(self.expected_entities),
            "graph_extracted_entities": float(self.extracted_entities),
            "graph_matched_entities": float(self.matched_entities),
            "entity_recall": self.entity_recall,
            "entity_precision": self.entity_precision,
            "graph_expected_relations": float(self.expected_relations),
            "graph_extracted_relations": float(self.extracted_relations),
            "graph_matched_relations": float(self.matched_relations),
            "relation_recall": self.relation_recall,
            "relation_precision": self.relation_precision,
        }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _relation_key(subject: str, predicate: str, object_: str) -> tuple[str, str, str]:
    return canonical_name(subject), canonical_name(predicate), canonical_name(object_)


def score_graph(extracted: GraphSnapshot, expected: GraphSnapshot) -> GraphQuality:
    """Score unique canonical nodes and directed typed relation triples."""
    expected_entities = {canonical_name(entity.name) for entity in expected.entities}
    extracted_entities = {canonical_name(entity.name) for entity in extracted.entities}
    matched_entities = expected_entities & extracted_entities

    expected_relations = {
        _relation_key(relation.subject, relation.predicate, relation.object)
        for relation in expected.relations
    }
    extracted_relations = {
        _relation_key(relation.subject, relation.predicate, relation.object)
        for relation in extracted.relations
    }
    matched_relations = expected_relations & extracted_relations
    return GraphQuality(
        expected_entities=len(expected_entities),
        extracted_entities=len(extracted_entities),
        matched_entities=len(matched_entities),
        entity_recall=_ratio(len(matched_entities), len(expected_entities)),
        entity_precision=_ratio(len(matched_entities), len(extracted_entities)),
        expected_relations=len(expected_relations),
        extracted_relations=len(extracted_relations),
        matched_relations=len(matched_relations),
        relation_recall=_ratio(len(matched_relations), len(expected_relations)),
        relation_precision=_ratio(len(matched_relations), len(extracted_relations)),
    )


__all__ = ["GraphQuality", "canonical_name", "score_graph"]
