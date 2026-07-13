"""Golden-set loading and validation (SPEC.md 8.5, 12.1)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from vaultledger.config import REPO_ROOT
from vaultledger.schemas import QAExample

DEFAULT_GOLDEN_PATH = REPO_ROOT / "vaultledger" / "evals" / "golden_set.yaml"


class GoldenSet(BaseModel):
    version: str
    examples: list[QAExample]


def golden_hash(path: str | Path = DEFAULT_GOLDEN_PATH) -> str:
    """Content hash recorded in every RunManifest."""
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw).hexdigest()


def load_golden_set(path: str | Path = DEFAULT_GOLDEN_PATH) -> GoldenSet:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
    return GoldenSet.model_validate(data)


def validate_expected_snippets(
    examples: list[QAExample],
    chunks_by_doc: dict[str, str],
) -> list[str]:
    """Return human-readable errors for missing expected doc/snippet anchors."""
    errors: list[str] = []
    for ex in examples:
        for doc_id in ex.expected_doc_ids:
            if doc_id not in chunks_by_doc:
                errors.append(f"{ex.id}: expected_doc_id {doc_id!r} is not in chunks")
        combined = "\n".join(chunks_by_doc.get(doc_id, "") for doc_id in ex.expected_doc_ids)
        for snippet in ex.expected_snippets:
            if snippet not in combined:
                errors.append(f"{ex.id}: expected_snippet not found: {snippet!r}")
    return errors


__all__ = [
    "DEFAULT_GOLDEN_PATH",
    "GoldenSet",
    "golden_hash",
    "load_golden_set",
    "validate_expected_snippets",
]
