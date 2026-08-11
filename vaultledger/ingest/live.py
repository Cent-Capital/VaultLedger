"""Isolated incremental ingestion for real user documents (Phase 16)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from vaultledger.config import Config, load_config
from vaultledger.graph.index import insert_lightrag_document
from vaultledger.graph.lightrag_io import load_lightrag_graphml
from vaultledger.graph.obsidian import export_obsidian_vault
from vaultledger.guardrails.input import injection_scan, pii_tagging_event, validate_file
from vaultledger.index.bm25 import Bm25Index
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.index.vector import VectorIndex
from vaultledger.schemas import Chunk, DocMeta

from .chunk import chunk_doc
from .classify import classify_doc_type
from .extract import ExtractionError, extract_record
from .ocr import OcrProcessingError, prepare_pdf
from .pii import PiiTagger
from .pipeline import _period_of, load_chunks
from .store import RecordStore


@dataclass
class LiveIngestResult:
    source_path: str
    doc_id: str
    status: Literal["ok", "partial", "failed"]
    chunks: int = 0
    ocr_derived: bool = False
    ocr_pages: list[int] = field(default_factory=list)
    embedded: bool = False
    graphed: bool = False
    replaced_existing: bool = False
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    graph_usage: dict[str, int | float | str] = field(default_factory=dict)
    error: str | None = None

    def as_receipt(self) -> dict:
        return {"timestamp": datetime.now(UTC).isoformat(), **asdict(self)}


def _within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _write_chunks(path: Path, chunks: list[Chunk]) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w") as handle:
        for chunk in chunks:
            # Same convention as the synthetic writer. User chunks carry a
            # non-default `corpus`, so their provenance is always serialized.
            handle.write(chunk.model_dump_json(exclude_defaults=True) + "\n")
    temp.replace(path)


def _append_receipt(index_dir: Path, result: LiveIngestResult) -> None:
    receipt_path = index_dir / "ingest_receipts.jsonl"
    with receipt_path.open("a") as handle:
        handle.write(json.dumps(result.as_receipt(), sort_keys=True) + "\n")


def _record_failed_document(index_dir: Path, path: Path, error: str) -> None:
    store = RecordStore(index_dir / "records.db")
    try:
        store.ensure_schema()
        existing = store.connect().execute(
            "SELECT 1 FROM documents WHERE doc_id = ?", (path.stem,)
        ).fetchone()
        if existing:
            return  # a transient re-ingest failure must not erase the last good version
        store.write_document(
            DocMeta(
                doc_id=path.stem,
                doc_type="unknown",
                source_filename=path.name,
                page_count=0,
                is_synthetic=False,
                corpus="user",
            ),
            parse_status="failed",
            error=error,
        )
    finally:
        store.close()


def _export_live_graph(graph_dir: Path, obsidian_dir: Path, chunks: list[Chunk]) -> None:
    graphmls = sorted(graph_dir.rglob("*.graphml"))
    if len(graphmls) != 1:
        raise RuntimeError(
            f"expected one live LightRAG GraphML artifact, found {len(graphmls)}"
        )
    snapshot = load_lightrag_graphml(graphmls[0])
    export_obsidian_vault(
        snapshot,
        document_ids=sorted({chunk.doc_id for chunk in chunks}),
        output_dir=obsidian_dir,
        replace=obsidian_dir.exists(),
    )


async def _insert_graph_with_timeout(
    cfg: Config,
    *,
    doc_id: str,
    chunks: list[Chunk],
    working_dir: Path,
    replace_existing: bool,
) -> dict:
    return await asyncio.wait_for(
        insert_lightrag_document(
            cfg,
            doc_id=doc_id,
            chunks=chunks,
            working_dir=working_dir,
            replace_existing=replace_existing,
        ),
        timeout=cfg.live.graph_timeout_seconds,
    )


def ingest_live_pdf(
    path: str | Path,
    config: Config | None = None,
    *,
    embed: bool = True,
    graph: bool = True,
) -> LiveIngestResult:
    """Incrementally ingest one inbox PDF into the isolated user corpus.

    Text extraction success is sufficient for retrieval. Typed financial-record
    extraction is best effort because genuine PDFs need not use the two synthetic
    layouts. OCR and graph failures remain explicit in the returned receipt.
    """
    cfg = config or load_config()
    live_paths = cfg.live_paths()  # safety gate precedes every directory creation
    source = Path(path).resolve()
    inbox = live_paths["inbox"]
    if not _within(source, inbox) or source == inbox:
        raise ValueError(f"live PDF must be inside the configured inbox {inbox}: {source}")
    if source.suffix.casefold() != ".pdf":
        raise ValueError(f"live ingest accepts PDF files only: {source.name}")

    index_dir = live_paths["index"]
    index_dir.mkdir(parents=True, exist_ok=True)
    result = LiveIngestResult(
        source_path=str(source),
        doc_id=source.stem,
        status="failed",
    )
    total_started = perf_counter()
    try:
        stage = perf_counter()
        file_event = validate_file(
            source.name,
            source.read_bytes(),
            max_bytes=cfg.guardrails.max_upload_bytes,
        )
        if file_event.action == "block":
            raise ValueError(file_event.details)
        result.stage_latency_ms["validate"] = round((perf_counter() - stage) * 1000, 3)

        embedder = OllamaEmbedder(
            model=cfg.embedding.model,
            base_url=cfg.embedding.ollama_url,
        )
        if embed and not embedder.is_available():
            raise RuntimeError(
                f"Ollama embedding model {cfg.embedding.model!r} is unavailable; "
                "start Ollama or use --no-embed for a non-answerable parse-only run"
            )

        stage = perf_counter()
        prepared = prepare_pdf(
            source,
            output_dir=index_dir / "ocr",
            timeout_seconds=cfg.live.ocr_timeout_seconds,
        )
        parsed = prepared.parsed
        result.ocr_derived = prepared.ocr_derived
        result.ocr_pages = list(prepared.ocr_pages)
        result.stage_latency_ms["parse_ocr"] = round((perf_counter() - stage) * 1000, 3)

        if not parsed.full_text.strip():
            raise OcrProcessingError("PDF has no readable text after preprocessing")
        stage = perf_counter()
        doc_type = classify_doc_type(parsed.full_text)
        record = None
        structured_error = None
        if doc_type != "unknown":
            try:
                record = extract_record(parsed, doc_type)
            except (ExtractionError, ValueError, KeyError, IndexError) as exc:
                structured_error = f"typed record unavailable; retrieval text retained: {exc}"
        tagger = PiiTagger()
        spans = tagger.analyze(parsed.full_text) if cfg.guardrails.pii_tagging else []
        pii_types = sorted({span.entity_type for span in spans})
        events = [file_event]
        if cfg.guardrails.pii_tagging:
            events.append(pii_tagging_event(spans))
        if cfg.guardrails.injection_scan:
            events.append(injection_scan(parsed.full_text))
        period_start, period_end = _period_of(record)
        meta = DocMeta(
            doc_id=parsed.doc_id,
            doc_type=doc_type,
            source_filename=parsed.source_filename,
            period_start=period_start,
            period_end=period_end,
            is_synthetic=False,
            page_count=parsed.page_count,
            pii_entity_types=pii_types,
            corpus="user",
            ocr_derived=prepared.ocr_derived,
            ocr_pages=list(prepared.ocr_pages),
        )
        document_chunks = chunk_doc(
            parsed,
            max_chars=cfg.chunking.max_chars,
            overlap_frac=cfg.chunking.overlap_frac,
        )
        if not document_chunks:
            raise OcrProcessingError("PDF produced no readable citation chunks")
        result.chunks = len(document_chunks)
        result.stage_latency_ms["extract_chunk"] = round((perf_counter() - stage) * 1000, 3)

        chunks_path = index_dir / "chunks.jsonl"
        existing_chunks = load_chunks(index_dir) if chunks_path.exists() else []
        result.replaced_existing = any(
            chunk.doc_id == parsed.doc_id for chunk in existing_chunks
        )
        all_chunks = [
            chunk for chunk in existing_chunks if chunk.doc_id != parsed.doc_id
        ] + document_chunks

        stage = perf_counter()
        store = RecordStore(index_dir / "records.db")
        try:
            store.ensure_schema()
            store.delete_document(parsed.doc_id)
            store.write_document(
                meta,
                parse_status="ok",
                error=structured_error,
                guardrail_events=events,
            )
            if record is not None:
                store.write_record(parsed.doc_id, record)
        finally:
            store.close()
        _write_chunks(chunks_path, all_chunks)
        bm25_path = index_dir / "bm25.json"
        sparse = Bm25Index.load(bm25_path) if bm25_path.exists() else Bm25Index.build([])
        sparse.upsert(document_chunks, replace_doc_id=parsed.doc_id)
        sparse.save(bm25_path)
        result.stage_latency_ms["store_bm25"] = round((perf_counter() - stage) * 1000, 3)

        if embed:
            stage = perf_counter()
            VectorIndex(index_dir / "chroma", embedder).upsert_document(
                parsed.doc_id,
                document_chunks,
            )
            result.embedded = True
            result.stage_latency_ms["vector"] = round((perf_counter() - stage) * 1000, 3)

        if graph:
            stage = perf_counter()
            graph_receipt = asyncio.run(
                _insert_graph_with_timeout(
                    cfg,
                    doc_id=parsed.doc_id,
                    chunks=document_chunks,
                    working_dir=live_paths["graph"],
                    replace_existing=result.replaced_existing,
                )
            )
            result.stage_latency_ms["graph"] = graph_receipt["wall_latency_ms"]
            result.graph_usage = graph_receipt
            _export_live_graph(live_paths["graph"], live_paths["obsidian"], all_chunks)
            result.stage_latency_ms["graph_and_projection"] = round(
                (perf_counter() - stage) * 1000,
                3,
            )
            result.graphed = True

        complete = (not embed or result.embedded) and (not graph or result.graphed)
        result.status = "ok" if complete else "partial"
    except Exception as exc:  # one bad user document must never stop the watcher
        result.error = str(exc)
        if result.chunks or result.embedded:
            result.status = "partial"
        else:
            _record_failed_document(index_dir, source, result.error)
            result.status = "failed"
    finally:
        result.stage_latency_ms["total"] = round((perf_counter() - total_started) * 1000, 3)
        _append_receipt(index_dir, result)
    return result


__all__ = ["LiveIngestResult", "ingest_live_pdf"]
