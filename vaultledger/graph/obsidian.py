"""Export a graph snapshot as a navigable Obsidian vault."""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

from .model import GraphRelation, GraphSnapshot

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.casefold()).strip("-") or "unnamed"


def _entity_note_names(snapshot: GraphSnapshot) -> dict[str, str]:
    """Assign collision-safe stable filenames to distinct extracted names."""
    used: dict[str, int] = {}
    names: dict[str, str] = {}
    for entity in sorted(snapshot.entities, key=lambda item: item.name):
        base = _slug(entity.name)
        used[base] = used.get(base, 0) + 1
        suffix = "" if used[base] == 1 else f"--{used[base]}"
        names[entity.name] = f"{base}{suffix}"
    return names


def _entity_link(name: str, note_names: dict[str, str]) -> str:
    note_name = note_names.get(name, _slug(name))
    return f"[[entities/{note_name}|{name}]]"


def _document_link(doc_id: str) -> str:
    return f"[[documents/{doc_id}|{doc_id}]]"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def export_obsidian_vault(
    snapshot: GraphSnapshot,
    *,
    document_ids: list[str],
    output_dir: str | Path,
    replace: bool = False,
) -> dict[str, int | str]:
    """Write one note per entity and document with relationship wikilinks."""
    output_dir = Path(output_dir)
    generated = [
        output_dir / "README.md",
        output_dir / "entities",
        output_dir / "documents",
        output_dir / ".obsidian",
    ]
    existing = [path for path in generated if path.exists()]
    if existing and not replace:
        raise FileExistsError(
            f"generated vault already exists at {output_dir}; pass replace=True to rebuild"
        )
    if replace:
        for path in existing:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    by_entity: dict[str, list[GraphRelation]] = defaultdict(list)
    by_document: dict[str, list[GraphRelation]] = defaultdict(list)
    note_names = _entity_note_names(snapshot)
    for relation in snapshot.relations:
        by_entity[relation.subject].append(relation)
        by_entity[relation.object].append(relation)
        for doc_id in relation.evidence_doc_ids:
            by_document[doc_id].append(relation)

    truth_warning = ""
    if snapshot.source == "ground_truth":
        truth_warning = (
            "> [!warning] Demo projection of Phase-1 ground truth. This is not "
            "LightRAG extraction evidence and must not be used to claim Phase-15 recall.\n\n"
        )
    _write(
        output_dir / "README.md",
        "# VaultLedger entity graph\n\n"
        + truth_warning
        + f"Source: `{snapshot.source}`\n\n"
        + f"- Entities: {len(snapshot.entities)}\n"
        + f"- Relations: {len(snapshot.relations)}\n"
        + f"- Documents: {len(document_ids)}\n\n"
        + "Open this folder as an Obsidian vault, then use Graph view. "
        + "Entity notes link across every evidence document.",
    )

    for entity in snapshot.entities:
        relation_lines = []
        for relation in sorted(
            by_entity[entity.name], key=lambda item: (item.predicate, item.subject, item.object)
        ):
            other = relation.object if relation.subject == entity.name else relation.subject
            direction = "→" if relation.subject == entity.name else "←"
            docs = ", ".join(_document_link(item) for item in relation.evidence_doc_ids)
            evidence = f" — evidence: {docs}" if docs else ""
            relation_lines.append(
                f"- `{relation.predicate}` {direction} "
                f"{_entity_link(other, note_names)}{evidence}"
            )
        if not relation_lines:
            relation_lines = [
                "- No scored ground-truth relation; entity is still present in the corpus."
            ]
        sources = sorted(set(entity.source_doc_ids))
        _write(
            output_dir / "entities" / f"{note_names[entity.name]}.md",
            f"# {entity.name}\n\n"
            f"Type: `{entity.kind}`\n\n"
            + (f"{entity.description}\n\n" if entity.description else "")
            + "## Relationships\n\n"
            + "\n".join(relation_lines)
            + "\n\n## Source documents\n\n"
            + ("\n".join(f"- {_document_link(item)}" for item in sources) or "- None recorded"),
        )

    for doc_id in sorted(set(document_ids)):
        relation_lines = []
        for relation in sorted(
            by_document[doc_id], key=lambda item: (item.predicate, item.subject, item.object)
        ):
            relation_lines.append(
                f"- {_entity_link(relation.subject, note_names)} — `{relation.predicate}` → "
                f"{_entity_link(relation.object, note_names)}"
            )
        _write(
            output_dir / "documents" / f"{doc_id}.md",
            f"# {doc_id}\n\n"
            "## Graph evidence\n\n"
            + ("\n".join(relation_lines) or "- No scored relation uses this document."),
        )

    # Obsidian recognizes the folder without this file, but keeping a minimal
    # config makes the generated artifact open directly in graph view.
    _write(output_dir / ".obsidian" / "graph.json", '{"collapse-filter":false,"showTags":false}')
    return {
        "source": snapshot.source,
        "entities": len(snapshot.entities),
        "relations": len(snapshot.relations),
        "documents": len(set(document_ids)),
    }


__all__ = ["export_obsidian_vault"]
