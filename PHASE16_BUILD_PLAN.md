# Phase 16 build plan — live documents, safely

Opened 2026-08-11 · Implements ADR-0011 and ADR-0012 · Status: **closed** — every
acceptance row discharged, including the scan arm, measured on a real image-only PDF

## Outcome

VaultLedger gains an isolated live-document path without changing the synthetic
evaluation population. A PDF dropped into an external inbox is validated, OCR'd
when necessary, chunked, added to lexical/vector/graph indexes incrementally, and
made answerable with exact citations. OCR-derived evidence remains visibly marked
from ingestion through the answer UI.

## Non-negotiable boundaries

- The live inbox, derived live index, live LightRAG working directory, and live
  Obsidian projection must all resolve outside the repository working tree.
- Existing `paths.pdfs`, `paths.index_dir`, `graph.working_dir`, and the eval CLI
  remain the synthetic, reproducible measurement path.
- OCR uses `ocrmypdf --skip-text`; no in-parser Tesseract geometry reconstruction.
- Missing OCR tooling turns an image-only document into an explicit failed ingest.
  It must never create an empty successful document.
- OCR-derived pages are marked on chunks and citations. No live or OCR-derived
  chunk is accepted by the eval corpus loader.
- Watcher and retry loops are bounded by typed configuration.

## Work packages

### 1. Configuration and safety gate

- Add typed `live` settings for inbox, index, graph, and Obsidian locations plus
  watcher polling/stability bounds.
- Expand `~`, require absolute resolved paths, reject every live path at or below
  the repository root, and reject overlapping live roots that could mix source and
  derived data.
- Run the safety check before creating directories or reading documents.

### 2. Provenance contracts and storage

- Extend document metadata with corpus (`synthetic`/`user`), OCR status, and OCR
  page numbers while retaining backwards-compatible schema defaults.
- Extend chunks and citations with OCR provenance so citation verification carries
  the flag from the matched source chunk rather than trusting model output.
- Persist the same fields in the live SQLite document table.

### 3. OCR preprocessing and real-PDF ingest

- Probe a PDF with the existing parser. If any page needs OCR, run
  `ocrmypdf --skip-text` into the external live index and parse the output.
- Refuse the document if OCR dependencies are unavailable, OCR exits non-zero, or
  a page remains unreadable after preprocessing.
- Permit unknown real-document layouts to remain retrieval-answerable even when no
  typed financial record can be extracted; typed extraction stays best effort.

### 4. Incremental indexes and watcher

- Upsert one document atomically into `chunks.jsonl`, SQLite, BM25, and Chroma;
  replace prior chunks for the same stable document id on re-ingest.
- Insert the same single document into the isolated live LightRAG index with its
  stable id instead of rebuilding the corpus.
- Record per-file stage and wall latency locally.
- Provide `scan-once` and a bounded polling watcher CLI. A file must have a stable
  size/mtime observation before ingest, preventing partial-copy reads.

### 5. Product boundary and warnings

- Show synthetic evaluation documents and user documents as separate library
  sources.
- Let Ask explicitly select the corpus and construct retrievers only from that
  corpus's index.
- Mark OCR-derived documents in the library and show a prominent warning whenever
  an answer cites OCR-derived evidence, especially for numeric verification.

## Acceptance tests

| Requirement | Deterministic proof |
|---|---|
| No live data inside repo | every protected live path rejects repo descendants before I/O |
| Text PDF works | a text-layer fixture is incrementally ingested with exact spans |
| OCR is gated | text PDFs never invoke OCR; scan fixtures invoke `--skip-text` |
| OCR failure is loud | missing/failed OCR tool produces a failed document and no chunks |
| Provenance survives | OCR page -> chunk -> verified citation carries `ocr_derived=true` |
| Evals stay synthetic | eval corpus loader rejects user/OCR chunks |
| Incremental update | a second document preserves the first; same id replaces, not duplicates |
| Watcher is safe | unstable files wait; stable files ingest; loop stops at configured bound |
| Graph is incremental | one document is passed to LightRAG `ainsert` with its stable id |
| UI is honest | app source contains corpus selector, user/synthetic boundary, and OCR warning |
| Regression safety | Ruff and the complete deterministic pytest suite pass |

## Phase close evidence

Phase 16 closes only after deterministic tests pass and an environment with Ollama,
LightRAG, `ocrmypdf`, and Tesseract produces a measured end-to-end receipt for both a
text-layer real PDF and a scan. Until that live receipt exists, the code path may be
complete but the real-environment acceptance criterion remains explicitly unverified.
