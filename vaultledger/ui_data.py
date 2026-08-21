"""Read-only, typed projections used by the Streamlit application."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class LibraryLoadError(RuntimeError):
    """The derived library index could not be rendered safely."""


@dataclass(frozen=True)
class LibraryDocument:
    doc_id: str
    doc_type: str
    period_start: str | None
    period_end: str | None
    page_count: int
    pii_entity_types: tuple[str, ...]
    guardrail_events: tuple[dict[str, Any], ...]
    parse_status: str
    corpus: str
    ocr_derived: bool
    ocr_pages: tuple[int, ...]

    def table_row(self) -> dict[str, object]:
        """Return the stable presentation row expected by the UI."""
        return {
            "Document": self.doc_id,
            "Type": self.doc_type,
            "Period": (
                f"{self.period_start} → {self.period_end}" if self.period_start else ""
            ),
            "Pages": self.page_count,
            "PII tags": len(self.pii_entity_types),
            "Guard flags": sum(
                event.get("action") != "pass" for event in self.guardrail_events
            ),
            "Source": "User" if self.corpus == "user" else "Synthetic",
            "OCR": (
                f"Scanned pages {list(self.ocr_pages)}"
                if self.ocr_derived
                else "Text layer"
            ),
            "Status": self.parse_status,
        }


@dataclass(frozen=True)
class LibrarySnapshot:
    documents: tuple[LibraryDocument, ...]
    chunks: int
    vector_index_built: bool

    @property
    def parse_failures(self) -> int:
        return sum(document.parse_status != "ok" for document in self.documents)


def _json_tuple(value: object, *, field: str, doc_id: str) -> tuple[Any, ...]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise LibraryLoadError(f"{doc_id} has invalid {field} metadata") from exc
    if not isinstance(parsed, list):
        raise LibraryLoadError(f"{doc_id} has non-list {field} metadata")
    return tuple(parsed)


def _load_documents(db_path: Path) -> tuple[LibraryDocument, ...]:
    try:
        with closing(sqlite3.connect(db_path)) as connection:
            connection.row_factory = sqlite3.Row
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents)")
            }
            optional = {
                "guardrail_events": (
                    "guardrail_events"
                    if "guardrail_events" in columns
                    else "'[]' AS guardrail_events"
                ),
                "corpus": "corpus" if "corpus" in columns else "'synthetic' AS corpus",
                "ocr_derived": (
                    "ocr_derived" if "ocr_derived" in columns else "0 AS ocr_derived"
                ),
                "ocr_pages": "ocr_pages" if "ocr_pages" in columns else "'[]' AS ocr_pages",
            }
            rows = connection.execute(
                "SELECT doc_id, doc_type, period_start, period_end, page_count, "
                f"pii_entity_types, {optional['guardrail_events']}, parse_status, "
                f"{optional['corpus']}, {optional['ocr_derived']}, {optional['ocr_pages']} "
                "FROM documents ORDER BY doc_id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise LibraryLoadError(f"could not read derived library index: {exc}") from exc

    documents = []
    for row in rows:
        doc_id = str(row["doc_id"])
        pii_types = _json_tuple(row["pii_entity_types"], field="PII", doc_id=doc_id)
        guardrails = _json_tuple(row["guardrail_events"], field="guardrail", doc_id=doc_id)
        ocr_pages = _json_tuple(row["ocr_pages"], field="OCR page", doc_id=doc_id)
        if not all(isinstance(value, str) for value in pii_types):
            raise LibraryLoadError(f"{doc_id} has invalid PII metadata")
        if not all(isinstance(value, dict) for value in guardrails):
            raise LibraryLoadError(f"{doc_id} has invalid guardrail metadata")
        if not all(isinstance(value, int) for value in ocr_pages):
            raise LibraryLoadError(f"{doc_id} has invalid OCR page metadata")
        documents.append(
            LibraryDocument(
                doc_id=doc_id,
                doc_type=str(row["doc_type"]),
                period_start=row["period_start"],
                period_end=row["period_end"],
                page_count=int(row["page_count"]),
                pii_entity_types=cast(tuple[str, ...], pii_types),
                guardrail_events=cast(tuple[dict[str, Any], ...], guardrails),
                parse_status=str(row["parse_status"]),
                corpus=str(row["corpus"]),
                ocr_derived=bool(row["ocr_derived"]),
                ocr_pages=cast(tuple[int, ...], ocr_pages),
            )
        )
    return tuple(documents)


def load_library_snapshot(index_dir: str | Path) -> LibrarySnapshot:
    """Load document and index status without leaking database work into the UI."""
    directory = Path(index_dir)
    documents = _load_documents(directory / "records.db")
    chunks_file = directory / "chunks.jsonl"
    chunks = 0
    if chunks_file.exists():
        with chunks_file.open(encoding="utf-8") as stream:
            chunks = sum(1 for _ in stream)
    return LibrarySnapshot(
        documents=documents,
        chunks=chunks,
        vector_index_built=(directory / "chroma").exists(),
    )


__all__ = [
    "LibraryDocument",
    "LibraryLoadError",
    "LibrarySnapshot",
    "load_library_snapshot",
]
