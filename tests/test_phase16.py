"""Phase 16 acceptance contracts for isolated live documents and OCR provenance."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fpdf import FPDF

from vaultledger.config import REPO_ROOT, LiveDocuments, load_config
from vaultledger.generate.reliable import verify_citations
from vaultledger.generate.schema import AnswerDraft, DraftCitation
from vaultledger.graph.index import _ainsert_one
from vaultledger.ingest.live import LiveIngestResult, ingest_live_pdf
from vaultledger.ingest.ocr import OcrUnavailableError, prepare_pdf
from vaultledger.ingest.parse import ParsedDoc, ParsedPage
from vaultledger.ingest.pipeline import assert_evaluation_corpus, load_chunks
from vaultledger.ingest.watcher import InboxWatcher
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk


def _live_config(tmp_path: Path):
    roots = {name: tmp_path / name for name in ("inbox", "index", "graph", "obsidian", "traces")}
    live = LiveDocuments(
        inbox_dir=str(roots["inbox"]),
        index_dir=str(roots["index"]),
        graph_working_dir=str(roots["graph"]),
        obsidian_dir=str(roots["obsidian"]),
        traces_dir=str(roots["traces"]),
        watcher_poll_seconds=0.001,
        watcher_stable_polls=2,
        watcher_max_polls=4,
        ocr_timeout_seconds=5,
    )
    return load_config().model_copy(update={"live": live}), roots


def _text_pdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, text)
    pdf.output(str(path))


class _NoPii:
    def analyze(self, text: str) -> list:
        return []


def test_live_paths_default_outside_repo_and_unsafe_config_refuses_startup():
    cfg = load_config()
    paths = cfg.live_paths()
    assert set(paths) == {"inbox", "index", "graph", "obsidian", "traces"}
    assert all(path.is_absolute() and not path.is_relative_to(REPO_ROOT) for path in paths.values())

    unsafe = cfg.model_copy(
        update={
            "live": cfg.live.model_copy(
                update={"inbox_dir": str(REPO_ROOT / "data" / "real-bank-statements")}
            )
        }
    )
    with pytest.raises(ValueError, match="outside the repository"):
        unsafe.live_paths()


def test_ocr_provenance_is_derived_from_verified_chunk_not_model_claim():
    chunk = Chunk(
        chunk_id="scan#c0",
        doc_id="scan",
        text="The scanned statement closing balance is $1,234.50.",
        page=2,
        char_start=0,
        char_end=51,
        corpus="user",
        ocr_derived=True,
    )
    draft = AnswerDraft(
        answer_text="The balance is $1,234.50.",
        citations=[
            DraftCitation(
                chunk_id="scan#c0",
                snippet="scanned statement closing balance is $1,234.50",
            )
        ],
    )
    verified = verify_citations(
        draft,
        [ScoredChunk(chunk=chunk, score=1.0, rank=1, source="test")],
    )
    assert verified.citations[0].corpus == "user"
    assert verified.citations[0].ocr_derived is True


def test_eval_loader_rejects_user_and_ocr_chunks(tmp_path: Path):
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    chunk = Chunk(
        chunk_id="user#c0",
        doc_id="user",
        text="private text",
        page=1,
        char_start=0,
        char_end=12,
        corpus="user",
    )
    (index_dir / "chunks.jsonl").write_text(chunk.model_dump_json() + "\n")
    with pytest.raises(ValueError, match="refusing to score"):
        assert_evaluation_corpus(index_dir)

    ocr_chunk = chunk.model_copy(update={"corpus": "synthetic", "ocr_derived": True})
    (index_dir / "chunks.jsonl").write_text(ocr_chunk.model_dump_json() + "\n")
    with pytest.raises(ValueError, match="OCR-derived"):
        assert_evaluation_corpus(index_dir)


def test_text_layer_pdf_bypasses_ocr_tools(tmp_path: Path):
    parsed = ParsedDoc(
        doc_id="native",
        source_filename="native.pdf",
        page_count=1,
        full_text="This is a readable native text-layer financial document.",
        pages=[ParsedPage(1, "This is a readable native text-layer financial document.", 0, 56)],
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("native text PDF must not probe or invoke OCR executables")

    result = prepare_pdf(
        tmp_path / "native.pdf",
        output_dir=tmp_path / "ocr",
        timeout_seconds=5,
        parser=lambda path: parsed,
        executable=should_not_run,
        runner=should_not_run,
    )
    assert result.processed_path == (tmp_path / "native.pdf").resolve()
    assert result.parsed.corpus == "user"
    assert not result.ocr_derived


def test_scanned_pdf_invokes_skip_text_and_preserves_original_identity(tmp_path: Path):
    source = tmp_path / "bank-scan.pdf"
    source.write_bytes(b"%PDF-fake")
    unreadable = ParsedDoc(
        doc_id="bank-scan",
        source_filename="bank-scan.pdf",
        page_count=1,
        full_text="",
        pages=[ParsedPage(1, "", 0, 0)],
        needs_ocr=True,
    )
    readable_text = "OCR recovered the statement balance of $1,234.50 exactly."
    readable = ParsedDoc(
        doc_id="temporary-output",
        source_filename="temporary-output.pdf",
        page_count=1,
        full_text=readable_text,
        pages=[ParsedPage(1, readable_text, 0, len(readable_text))],
    )
    calls = []

    def parser(path):
        return unreadable if Path(path).resolve() == source.resolve() else readable

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"%PDF-ocr")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = prepare_pdf(
        source,
        output_dir=tmp_path / "external-index" / "ocr",
        timeout_seconds=5,
        parser=parser,
        executable=lambda name: f"/usr/local/bin/{name}",
        runner=runner,
    )
    assert calls and "--skip-text" in calls[0][0]
    assert result.parsed.doc_id == "bank-scan"
    assert result.parsed.source_filename == "bank-scan.pdf"
    assert result.parsed.ocr_pages == (1,)
    assert result.ocr_derived
    assert result.processed_path.name == "bank-scan.ocr.pdf"


def test_scanned_pdf_fails_clearly_when_ocr_dependency_is_missing(tmp_path: Path):
    unreadable = ParsedDoc(
        doc_id="scan",
        source_filename="scan.pdf",
        page_count=1,
        full_text="",
        pages=[ParsedPage(1, "", 0, 0)],
        needs_ocr=True,
    )
    with pytest.raises(OcrUnavailableError, match="tesseract"):
        prepare_pdf(
            tmp_path / "scan.pdf",
            output_dir=tmp_path / "ocr",
            timeout_seconds=5,
            parser=lambda path: unreadable,
            executable=lambda name: "/bin/ocrmypdf" if name == "ocrmypdf" else None,
        )


def test_live_ingest_adds_and_replaces_text_pdfs_incrementally(tmp_path: Path, monkeypatch):
    cfg, roots = _live_config(tmp_path)
    monkeypatch.setattr("vaultledger.ingest.live.PiiTagger", _NoPii)
    first = roots["inbox"] / "first.pdf"
    second = roots["inbox"] / "second.pdf"
    _text_pdf(first, "First private document states the verified amount is $10.00 today.")
    _text_pdf(second, "Second private document states the verified amount is $20.00 today.")

    first_result = ingest_live_pdf(first, cfg, embed=False, graph=False)
    second_result = ingest_live_pdf(second, cfg, embed=False, graph=False)
    assert first_result.status == second_result.status == "ok"
    chunks = load_chunks(roots["index"])
    assert {chunk.doc_id for chunk in chunks} == {"first", "second"}
    assert all(chunk.corpus == "user" and not chunk.ocr_derived for chunk in chunks)

    _text_pdf(first, "First private document was updated; verified amount is $30.00 today.")
    replaced = ingest_live_pdf(first, cfg, embed=False, graph=False)
    chunks = load_chunks(roots["index"])
    assert replaced.replaced_existing is True
    assert len([chunk for chunk in chunks if chunk.doc_id == "first"]) == replaced.chunks
    assert any("$30.00" in chunk.text for chunk in chunks if chunk.doc_id == "first")
    assert not any("$10.00" in chunk.text for chunk in chunks if chunk.doc_id == "first")

    receipt_lines = (roots["index"] / "ingest_receipts.jsonl").read_text().splitlines()
    receipts = [json.loads(line) for line in receipt_lines]
    assert len(receipts) == 3
    assert all(receipt["stage_latency_ms"]["total"] >= 0 for receipt in receipts)


def test_watcher_waits_for_stability_and_reingests_only_after_change(tmp_path: Path):
    cfg, roots = _live_config(tmp_path)
    source = roots["inbox"] / "drop.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-incomplete")
    calls = []

    def fake_ingest(path, config, *, embed, graph):
        calls.append((Path(path), embed, graph))
        return LiveIngestResult(str(path), Path(path).stem, "ok", chunks=1)

    watcher = InboxWatcher(cfg, embed=False, graph=False, ingest=fake_ingest, sleep=lambda _: None)
    assert watcher.poll_once() == []
    assert len(watcher.poll_once()) == 1
    assert watcher.poll_once() == []
    source.write_bytes(b"%PDF-complete-and-changed")
    assert watcher.poll_once() == []
    assert len(watcher.poll_once()) == 1
    assert len(calls) == 2

    restarted = InboxWatcher(
        cfg,
        embed=False,
        graph=False,
        ingest=fake_ingest,
        sleep=lambda _: None,
    )
    assert restarted.poll_once() == []
    assert restarted.poll_once() == []
    assert len(calls) == 2


def test_incremental_graph_helper_uses_stable_id_and_optional_replace():
    class FakeRag:
        def __init__(self):
            self.calls = []

        async def initialize_storages(self):
            self.calls.append("initialize")

        async def adelete_by_doc_id(self, doc_id):
            self.calls.append(("delete", doc_id))
            return SimpleNamespace(status="not_found")

        async def ainsert(self, documents, *, ids, file_paths):
            self.calls.append(("insert", documents, ids, file_paths))

        async def finalize_storages(self):
            self.calls.append("finalize")

    rag = FakeRag()
    asyncio.run(
        _ainsert_one(
            rag,
            doc_id="live-doc",
            document="verbatim source text",
            replace_existing=True,
        )
    )
    assert rag.calls == [
        "initialize",
        ("delete", "live-doc"),
        ("insert", ["verbatim source text"], ["live-doc"], ["live-doc"]),
        "finalize",
    ]


def test_phase16_ui_keeps_corpus_boundary_and_ocr_warning_visible():
    app = (REPO_ROOT / "app" / "streamlit_app.py").read_text()
    assert "Synthetic evaluation corpus" in app
    assert "User documents" in app
    assert "OCR can misread digits" in app
    assert "citation.ocr_derived" in app


def test_provenance_schema_did_not_move_the_synthetic_corpus_hash():
    """Phase 16 added provenance fields; the synthetic corpus bytes must not move.

    Every committed receipt cites `corpus_hash` over `chunks.jsonl`. Serializing the
    new `corpus`/`ocr_derived` defaults would have changed that hash on the next
    ingest while the chunk content stayed identical, so a reader comparing receipts
    across the Phase-16 boundary would see a corpus that appeared to have changed.
    """
    synthetic = Chunk(
        chunk_id="a#c0", doc_id="a", text="t", page=1, char_start=0, char_end=1
    )
    emitted = json.loads(synthetic.model_dump_json(exclude_defaults=True))
    assert "corpus" not in emitted and "ocr_derived" not in emitted
    assert set(emitted) == {"chunk_id", "doc_id", "text", "page", "char_start", "char_end"}


def test_user_chunks_always_serialize_provenance_for_the_eval_guard():
    """`assert_evaluation_corpus` reads `corpus`, so a user chunk must persist it."""
    user = Chunk(
        chunk_id="b#c0", doc_id="b", text="t", page=1, char_start=0, char_end=1, corpus="user"
    )
    line = user.model_dump_json(exclude_defaults=True)
    assert '"corpus":"user"' in line
    assert Chunk.model_validate_json(line).corpus == "user"


def test_ocr_page_threshold_is_shared_not_restated():
    """A drifted second threshold would OCR a page without marking it (ADR-0012)."""
    from vaultledger.ingest import ocr as ocr_module
    from vaultledger.ingest.parse import MIN_PAGE_TEXT_CHARS

    assert ocr_module.MIN_PAGE_TEXT_CHARS is MIN_PAGE_TEXT_CHARS
    assert "< 20" not in (REPO_ROOT / "vaultledger" / "ingest" / "ocr.py").read_text()
