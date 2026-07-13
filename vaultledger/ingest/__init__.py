"""Ingestion pipeline: parse -> type/extract -> SQLite -> PII-tag -> chunk (Phase 2, SPEC 9)."""

from .pipeline import IngestResult, load_chunks, run_ingest

__all__ = ["run_ingest", "load_chunks", "IngestResult"]
