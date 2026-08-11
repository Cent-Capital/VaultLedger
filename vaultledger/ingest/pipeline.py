"""Ingestion pipeline orchestrator (SPEC.md Section 9 steps 1-5).

parse -> classify -> extract -> SQLite -> PII-tag -> chunk -> index (Chroma +
BM25). One bad document is recorded as failed and skipped — a single corrupt
upload must never abort the batch (SPEC 13.1 file_validation spirit).

Artifacts land under ``paths.index_dir`` (derived data, rebuildable):
  records.db     — typed records + doc metadata (SQLite)
  chunks.jsonl   — every chunk with exact spans (the retrieval corpus)
  bm25.json      — tokenized corpus for the lexical index
  chroma/        — persistent vector store

Embedding requires Ollama; ``embed=False`` builds everything else (used by CI,
which has no model runtime — the vector index is then built lazily on the
next full run).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from vaultledger.config import Config, load_config
from vaultledger.guardrails.input import (
    injection_scan,
    pii_tagging_event,
    validate_file,
)
from vaultledger.index.bm25 import Bm25Index
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.index.vector import VectorIndex
from vaultledger.schemas import Chunk, DocMeta

from .chunk import chunk_doc
from .classify import classify_doc_type
from .extract import ExtractionError, extract_record
from .parse import parse_pdf
from .pii import PiiTagger
from .records import PayStubRecord, StatementRecord
from .store import RecordStore


@dataclass
class IngestResult:
    docs_ok: int = 0
    docs_failed: int = 0
    chunks: int = 0
    embedded: bool = False
    failures: list[str] = field(default_factory=list)


def _period_of(record: object) -> tuple[date | None, date | None]:
    """Best-effort document period for DocMeta (statements + pay stubs)."""
    if isinstance(record, StatementRecord):
        return record.period_start, record.period_end
    if isinstance(record, PayStubRecord):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", record.pay_period)
        if m:
            return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    return None, None


def run_ingest(config: Config | None = None, embed: bool = True) -> IngestResult:
    cfg = config or load_config()
    pdf_dir = cfg.repo_path(cfg.paths.pdfs)
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"no PDFs found in {pdf_dir} — run `make data` first")

    store = RecordStore(index_dir / "records.db")
    store.init_schema()
    tagger = PiiTagger()
    result = IngestResult()
    all_chunks: list[Chunk] = []

    for path in pdfs:
        ingest_events = []
        try:
            if cfg.guardrails.file_validation:
                file_event = validate_file(
                    path.name,
                    path.read_bytes(),
                    max_bytes=cfg.guardrails.max_upload_bytes,
                )
                ingest_events.append(file_event)
                if file_event.action == "block":
                    raise ValueError(file_event.details)
            parsed = parse_pdf(path)
            doc_type = classify_doc_type(parsed.full_text)
            record = extract_record(parsed, doc_type)
            spans = tagger.analyze(parsed.full_text) if cfg.guardrails.pii_tagging else []
            pii_types = sorted({span.entity_type for span in spans})
            if cfg.guardrails.pii_tagging:
                ingest_events.append(pii_tagging_event(spans))
            if cfg.guardrails.injection_scan:
                ingest_events.append(injection_scan(parsed.full_text))
            period_start, period_end = _period_of(record)
            meta = DocMeta(
                doc_id=parsed.doc_id,
                doc_type=doc_type,
                source_filename=parsed.source_filename,
                period_start=period_start,
                period_end=period_end,
                page_count=parsed.page_count,
                pii_entity_types=pii_types,
                corpus="synthetic",
            )
            chunks = chunk_doc(
                parsed,
                max_chars=cfg.chunking.max_chars,
                overlap_frac=cfg.chunking.overlap_frac,
            )
            store.write_document(meta, parse_status="ok", guardrail_events=ingest_events)
            store.write_record(parsed.doc_id, record)
            all_chunks.extend(chunks)
            result.docs_ok += 1
        except (ExtractionError, ValueError, KeyError, IndexError) as exc:
            # Never crash the batch on one bad document; record and continue.
            meta = DocMeta(
                doc_id=path.stem,
                doc_type="unknown",
                source_filename=path.name,
                page_count=0,
            )
            store.write_document(
                meta,
                parse_status="failed",
                error=str(exc),
                guardrail_events=ingest_events,
            )
            result.docs_failed += 1
            result.failures.append(f"{path.stem}: {exc}")

    with open(index_dir / "chunks.jsonl", "w") as f:
        for chunk in all_chunks:
            # exclude_defaults keeps the synthetic corpus byte-identical across the
            # Phase-16 provenance schema change, so `corpus_hash` in every committed
            # receipt still identifies this corpus. Chunk's six positional fields are
            # required and always emitted; only `corpus`/`ocr_derived` can be omitted,
            # and only when they equal the synthetic defaults a reader assumes anyway.
            f.write(chunk.model_dump_json(exclude_defaults=True) + "\n")
    result.chunks = len(all_chunks)

    Bm25Index.build(all_chunks).save(index_dir / "bm25.json")

    if embed:
        embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
        if not embedder.is_available():
            raise RuntimeError(
                f"Ollama not reachable or model {cfg.embedding.model!r} not pulled; "
                "run `ollama pull nomic-embed-text`, or pass --no-embed"
            )
        VectorIndex(index_dir / "chroma", embedder).build(all_chunks)
        result.embedded = True

    store.close()
    return result


def load_chunks(index_dir: str | Path) -> list[Chunk]:
    """Read back the chunk corpus written by ``run_ingest``."""
    chunks = []
    with open(Path(index_dir) / "chunks.jsonl") as f:
        for line in f:
            chunks.append(Chunk.model_validate_json(line))
    return chunks


def assert_evaluation_corpus(index_dir: str | Path) -> list[Chunk]:
    """Refuse user or OCR-derived chunks in any measured evaluation run."""
    chunks = load_chunks(index_dir)
    invalid = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.corpus != "synthetic" or chunk.ocr_derived
    ]
    if invalid:
        sample = ", ".join(invalid[:3])
        raise ValueError(
            "evaluation corpus contains user or OCR-derived chunks; "
            f"refusing to score ({sample})"
        )
    return chunks


__all__ = ["run_ingest", "load_chunks", "assert_evaluation_corpus", "IngestResult"]
