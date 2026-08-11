"""Load the committed Phase-1 graph as Phase-15 evaluation ground truth."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .model import GraphEntity, GraphRelation, GraphSnapshot


def _scoreable_entities(data: dict) -> dict[str, tuple[str, str | None]]:
    """Return the entity population named by SPEC 14.3.

    Addresses are attributes in ``entities.json``, not headline graph entity
    types.  Relation endpoints are also not used to invent the denominator:
    one ``shared_address`` object is explanatory prose rather than an entity.
    The denominator is therefore people + organizations + merchants + accounts.
    """
    entities: dict[str, tuple[str, str | None]] = {}
    for persona in data["personas"]:
        entities[persona["name"]] = ("person", None)
        for account in persona.get("accounts", []):
            entities[f"{account['label']} ****{account['last4']}"] = (
                "account",
                str(account["last4"]),
            )
    for organization in data["organizations"]:
        entities[organization["name"]] = (str(organization["kind"]), None)
    for merchant in data["recurring_merchants"]:
        entities[merchant] = ("merchant", None)
    return entities


def load_ground_truth(path: str | Path) -> GraphSnapshot:
    path = Path(path)
    data = json.loads(path.read_text())
    relations = tuple(
        GraphRelation(
            subject=str(item["subject"]),
            predicate=str(item["type"]),
            object=str(item["object"]),
            evidence_doc_ids=tuple(sorted(set(item.get("evidence_docs", [])))),
        )
        for item in data["relations"]
    )
    evidence: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        evidence[relation.subject].update(relation.evidence_doc_ids)
        evidence[relation.object].update(relation.evidence_doc_ids)
    entities = tuple(
        GraphEntity(
            name=name,
            kind=kind,
            source_doc_ids=tuple(sorted(evidence[name])),
            account_last4=last4,
        )
        for name, (kind, last4) in sorted(_scoreable_entities(data).items())
    )
    return GraphSnapshot(source="ground_truth", entities=entities, relations=relations)


__all__ = ["load_ground_truth"]
