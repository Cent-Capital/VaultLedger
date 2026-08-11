"""Deterministic graph extraction metrics against ``entities.json``."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .model import GraphEntity, GraphSnapshot

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


@dataclass(frozen=True)
class AccountAliasQuality:
    """Entity quality under ADR-0009's type-scoped account alias rule.

    ``quality.entity_precision`` uses one true positive per distinct expected
    entity. ``node_counted_entity_precision`` is exposed only to reproduce the
    alternative diagnostic convention; duplicate aliases therefore remain
    visible rather than silently improving the chosen precision result.
    """

    quality: GraphQuality
    alias_matched_expected: int
    alias_credited_nodes: int
    duplicate_alias_nodes: int
    node_counted_matched_entities: int
    node_counted_entity_precision: float
    precision_convention: str = "distinct_expected_one_credit_per_account"
    alias_rule: str = "account_last4_masked_or_ending_in"

    def as_metrics(self) -> dict[str, float | str]:
        return {
            **self.quality.as_metrics(),
            "account_alias_matched_expected": float(self.alias_matched_expected),
            "account_alias_credited_nodes": float(self.alias_credited_nodes),
            "account_alias_duplicate_nodes": float(self.duplicate_alias_nodes),
            "node_counted_matched_entities": float(self.node_counted_matched_entities),
            "node_counted_entity_precision": self.node_counted_entity_precision,
            "precision_convention": self.precision_convention,
            "alias_rule": self.alias_rule,
        }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _relation_key(subject: str, predicate: str, object_: str) -> tuple[str, str, str]:
    return canonical_name(subject), canonical_name(predicate), canonical_name(object_)


def account_alias_patterns(last4: str) -> tuple[str, str]:
    """Build the inspectable aliases from ground-truth ``account.last4``.

    The boundary prevents ``4021`` from matching a substring of ``40210``.
    Only a four-digit value from the structured schema is accepted.
    """
    if not re.fullmatch(r"\d{4}", last4):
        raise ValueError("account last4 must contain exactly four digits")
    escaped = re.escape(last4)
    return rf"\*{{2,}}\s*{escaped}\b", rf"ending\s+in\s+{escaped}\b"


def account_alias_table(expected: GraphSnapshot) -> dict[str, tuple[str, str]]:
    """Return expected canonical account name -> explicit regex aliases."""
    return {
        canonical_name(entity.name): account_alias_patterns(entity.account_last4)
        for entity in expected.entities
        if entity.kind.casefold() == "account" and entity.account_last4 is not None
    }


def _entity_sets(snapshot: GraphSnapshot) -> set[str]:
    return {canonical_name(entity.name) for entity in snapshot.entities}


def _expected_by_name(snapshot: GraphSnapshot) -> dict[str, GraphEntity]:
    return {canonical_name(entity.name): entity for entity in snapshot.entities}


def score_graph(extracted: GraphSnapshot, expected: GraphSnapshot) -> GraphQuality:
    """Score unique canonical nodes and directed typed relation triples."""
    expected_entities = _entity_sets(expected)
    extracted_entities = _entity_sets(extracted)
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


def score_graph_with_account_aliases(
    extracted: GraphSnapshot,
    expected: GraphSnapshot,
) -> AccountAliasQuality:
    """Apply only ADR-0009 aliases, with duplicate nodes costing precision."""
    strict = score_graph(extracted, expected)
    expected_by_name = _expected_by_name(expected)
    extracted_entities = _entity_sets(extracted)
    strict_matches = set(expected_by_name) & extracted_entities
    aliases = account_alias_table(expected)

    alias_matches: dict[str, set[str]] = {}
    for expected_name, patterns in aliases.items():
        if expected_name in strict_matches:
            continue
        matches = {
            extracted_name
            for extracted_name in extracted_entities
            if any(re.search(pattern, extracted_name, flags=re.IGNORECASE) for pattern in patterns)
        }
        if matches:
            alias_matches[expected_name] = matches

    alias_nodes = set().union(*alias_matches.values()) if alias_matches else set()
    matched_expected = strict_matches | set(alias_matches)
    # One credit per expected account is the selected precision convention.
    # Additional alias nodes stay in the denominator and are reported below.
    quality = GraphQuality(
        expected_entities=strict.expected_entities,
        extracted_entities=strict.extracted_entities,
        matched_entities=len(matched_expected),
        entity_recall=_ratio(len(matched_expected), strict.expected_entities),
        entity_precision=_ratio(len(matched_expected), strict.extracted_entities),
        expected_relations=strict.expected_relations,
        extracted_relations=strict.extracted_relations,
        matched_relations=strict.matched_relations,
        relation_recall=strict.relation_recall,
        relation_precision=strict.relation_precision,
    )
    node_counted_matches = len(strict_matches) + len(alias_nodes)
    return AccountAliasQuality(
        quality=quality,
        alias_matched_expected=len(alias_matches),
        alias_credited_nodes=len(alias_nodes),
        duplicate_alias_nodes=sum(max(0, len(matches) - 1) for matches in alias_matches.values()),
        node_counted_matched_entities=node_counted_matches,
        node_counted_entity_precision=_ratio(node_counted_matches, strict.extracted_entities),
    )


__all__ = [
    "AccountAliasQuality",
    "GraphQuality",
    "account_alias_patterns",
    "account_alias_table",
    "canonical_name",
    "score_graph",
    "score_graph_with_account_aliases",
]
