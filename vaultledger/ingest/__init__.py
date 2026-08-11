"""Ingestion pipeline: parse -> type/extract -> SQLite -> PII-tag -> chunk (Phase 2, SPEC 9)."""

from .pipeline import IngestResult, assert_evaluation_corpus, load_chunks, run_ingest

__all__ = [
    "IngestResult",
    "assert_evaluation_corpus",
    "load_chunks",
    "run_ingest",
]
