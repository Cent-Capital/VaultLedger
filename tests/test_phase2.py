"""Phase 2 acceptance criteria as tests (SPEC.md Section 16, Phase 2).

AC: all docs ingested; chunks carry exact spans; typed records validate; PII
tags stored; manual similarity query sane.

"Typed records validate" is enforced the strong way: every extracted record is
compared field-by-field against the ground-truth JSON — which the extractor
never reads (it parses only the rendered PDF text). The corpus is built fresh
into a temp dir, so these tests also prove the pipeline runs end-to-end from
nothing but PDFs.

The vector-index test needs Ollama + nomic-embed-text and is skipped where
they are absent (CI); everything else is deterministic and runs everywhere.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from vaultledger.config import Paths, load_config
from vaultledger.index.bm25 import Bm25Index
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.index.vector import VectorIndex
from vaultledger.ingest.parse import parse_pdf
from vaultledger.ingest.pipeline import load_chunks, run_ingest
from vaultledger.synth.build import build
from vaultledger.synth.records import ADVERSARIAL_LINE

SEED = 42


# --- Fixtures ----------------------------------------------------------------
@pytest.fixture(scope="module")
def ingested(tmp_path_factory):
    """Build the corpus fresh, ingest it (no embedding), return all artifacts."""
    out = tmp_path_factory.mktemp("corpus")
    build(out_dir=out, seed=SEED)
    index_dir = out / "index"

    cfg = load_config().model_copy(
        update={
            "paths": Paths(
                pdfs=str(out / "synthetic_pdfs"),
                ground_truth=str(out / "ground_truth"),
                index_dir=str(index_dir),
            )
        }
    )
    result = run_ingest(cfg, embed=False)

    gt = {}
    for p in sorted((out / "ground_truth").glob("*.json")):
        if p.name != "entities.json":
            gt[p.stem] = json.loads(p.read_text())

    conn = sqlite3.connect(index_dir / "records.db")
    conn.row_factory = sqlite3.Row
    return {
        "cfg": cfg,
        "result": result,
        "gt": gt,
        "conn": conn,
        "index_dir": index_dir,
        "pdf_dir": out / "synthetic_pdfs",
        "chunks": load_chunks(index_dir),
    }


# --- AC: all docs ingested -----------------------------------------------------
def test_all_docs_ingested_without_failures(ingested):
    result = ingested["result"]
    assert result.docs_failed == 0, f"failures: {result.failures}"
    assert result.docs_ok == len(ingested["gt"])
    rows = ingested["conn"].execute("SELECT parse_status FROM documents").fetchall()
    assert len(rows) == len(ingested["gt"])
    assert all(r["parse_status"] == "ok" for r in rows)


def test_doc_types_match_ground_truth(ingested):
    rows = ingested["conn"].execute("SELECT doc_id, doc_type FROM documents").fetchall()
    for r in rows:
        assert r["doc_type"] == ingested["gt"][r["doc_id"]]["doc_type"], r["doc_id"]


# --- AC: chunks carry exact spans ----------------------------------------------
def test_every_chunk_is_an_exact_span_of_its_document(ingested):
    full_texts = {
        p.stem: parse_pdf(p).full_text for p in sorted(ingested["pdf_dir"].glob("*.pdf"))
    }
    assert ingested["chunks"], "no chunks produced"
    for c in ingested["chunks"]:
        assert full_texts[c.doc_id][c.char_start : c.char_end] == c.text, c.chunk_id


def test_chunk_page_attribution_is_correct(ingested):
    parsed = {p.stem: parse_pdf(p) for p in sorted(ingested["pdf_dir"].glob("*.pdf"))}
    for c in ingested["chunks"]:
        page = parsed[c.doc_id].pages[c.page - 1]
        assert page.char_start <= c.char_start and c.char_end <= page.char_end, c.chunk_id


def test_chunks_respect_size_budget_and_line_alignment(ingested):
    max_chars = ingested["cfg"].chunking.max_chars
    for c in ingested["chunks"]:
        assert 0 < len(c.text) <= max_chars, c.chunk_id
        assert not c.text.startswith("\n") and not c.text.endswith("\n"), c.chunk_id


# --- AC: typed records validate (scored against ground truth) -------------------
def _gt_of_type(ingested, doc_type):
    return {k: v for k, v in ingested["gt"].items() if v["doc_type"] == doc_type}


def test_statement_records_match_ground_truth(ingested):
    conn = ingested["conn"]
    for doc_id, gt in _gt_of_type(ingested, "bank_statement").items():
        rec = gt["record"]
        row = conn.execute(
            "SELECT * FROM bank_statements WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        assert row is not None, doc_id
        assert row["account_holder"] == rec["account_holder"]
        assert row["account_last4"] == rec["account_last4"]
        assert row["account_type"] == rec["account_type"]
        assert row["opening_balance"] == pytest.approx(rec["opening_balance"])
        assert row["closing_balance"] == pytest.approx(rec["closing_balance"])
        assert row["period_start"] == rec["period_start"]
        assert row["period_end"] == rec["period_end"]

        txns = conn.execute(
            "SELECT date, description, amount, type FROM transactions "
            "WHERE doc_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()
        assert len(txns) == len(rec["transactions"]), doc_id
        for got, want in zip(txns, rec["transactions"], strict=True):
            assert got["date"] == want["date"]
            assert got["amount"] == pytest.approx(want["amount"])
            assert got["type"] == want["type"], (doc_id, want["description"])
            # Renderers truncate long descriptions; extracted must be a prefix.
            assert want["description"].startswith(got["description"])


def test_1099_records_match_ground_truth(ingested):
    conn = ingested["conn"]
    for doc_id, gt in _gt_of_type(ingested, "form_1099").items():
        rec = gt["record"]
        row = conn.execute("SELECT * FROM forms_1099 WHERE doc_id = ?", (doc_id,)).fetchone()
        assert row is not None, doc_id
        assert row["payer_name"] == rec["payer_name"]
        assert row["recipient_name"] == rec["recipient_name"]
        assert row["tax_year"] == int(rec["tax_year"])
        box1 = conn.execute(
            "SELECT amount FROM form_1099_boxes WHERE doc_id = ? AND box = '1'", (doc_id,)
        ).fetchone()
        assert box1["amount"] == pytest.approx(rec["box_amounts"]["1"])


def test_invoice_records_match_ground_truth(ingested):
    conn = ingested["conn"]
    for doc_id, gt in _gt_of_type(ingested, "invoice").items():
        rec = gt["record"]
        printed_total = gt["entities"].get("printed_total", rec["total"])
        row = conn.execute("SELECT * FROM invoices WHERE doc_id = ?", (doc_id,)).fetchone()
        assert row is not None, doc_id
        assert row["vendor"] == rec["vendor"]
        assert row["invoice_number"] == rec["invoice_number"]
        assert row["due_date"] == rec["due_date"]
        assert row["total"] == pytest.approx(printed_total)
        if row["issue_date"] is not None:  # layout B prints no issue date
            assert row["issue_date"] == rec["issue_date"]

        items = conn.execute(
            "SELECT desc, qty, unit_price, amount FROM invoice_line_items "
            "WHERE doc_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()
        assert len(items) == len(rec["line_items"]), doc_id
        for got, want in zip(items, rec["line_items"], strict=True):
            assert want["desc"].startswith(got["desc"])
            assert got["qty"] == want["qty"]
            assert got["unit_price"] == pytest.approx(want["unit_price"])
            assert got["amount"] == pytest.approx(want["amount"])


def test_paystub_records_match_ground_truth(ingested):
    conn = ingested["conn"]
    for doc_id, gt in _gt_of_type(ingested, "pay_stub").items():
        rec = gt["record"]
        row = conn.execute("SELECT * FROM pay_stubs WHERE doc_id = ?", (doc_id,)).fetchone()
        assert row is not None, doc_id
        assert row["employer"] == rec["employer"]
        assert row["employee"] == rec["employee"]
        assert row["gross_pay"] == pytest.approx(rec["gross_pay"])
        assert row["net_pay"] == pytest.approx(rec["net_pay"])
        deductions = {
            r["name"]: r["amount"]
            for r in conn.execute(
                "SELECT name, amount FROM pay_stub_deductions WHERE doc_id = ?", (doc_id,)
            )
        }
        assert deductions == pytest.approx(rec["deductions"]), doc_id


def test_seeded_wrong_total_survives_extraction(ingested):
    """The defect doc's *printed* total must be stored as printed — the numeric
    verifier (Phase 13) can only catch the discrepancy if extraction is honest."""
    conn = ingested["conn"]
    mismatches = []
    for doc_id, gt in _gt_of_type(ingested, "invoice").items():
        printed = gt["entities"].get("printed_total")
        if printed is not None and printed != pytest.approx(gt["record"]["total"]):
            row = conn.execute("SELECT total FROM invoices WHERE doc_id = ?", (doc_id,)).fetchone()
            items_sum = conn.execute(
                "SELECT SUM(amount) AS s FROM invoice_line_items WHERE doc_id = ?", (doc_id,)
            ).fetchone()["s"]
            assert row["total"] == pytest.approx(printed)
            assert row["total"] != pytest.approx(items_sum)
            mismatches.append(doc_id)
    assert mismatches, "the seeded wrong-total invoice was not found"


# --- AC: PII tags stored ---------------------------------------------------------
def test_every_doc_has_pii_tags(ingested):
    rows = ingested["conn"].execute("SELECT doc_id, pii_entity_types FROM documents").fetchall()
    for r in rows:
        tags = json.loads(r["pii_entity_types"])
        assert tags, f"{r['doc_id']}: no PII tags stored"


def test_person_and_account_tags_present(ingested):
    conn = ingested["conn"]
    rows = conn.execute("SELECT doc_id, doc_type, pii_entity_types FROM documents").fetchall()
    tagged_person = [r for r in rows if "PERSON" in json.loads(r["pii_entity_types"])]
    # spaCy-small misses the odd name; require near-universal, not perfect.
    assert len(tagged_person) >= 0.9 * len(rows)
    for r in rows:
        if r["doc_type"] == "bank_statement":
            assert "US_BANK_NUMBER" in json.loads(r["pii_entity_types"]), r["doc_id"]


# --- Adversarial doc flows through, as data ---------------------------------------
def test_injection_line_lands_in_a_chunk_verbatim(ingested):
    poisoned = [c for c in ingested["chunks"] if ADVERSARIAL_LINE in c.text]
    assert poisoned, "the embedded injection line did not survive into any chunk"


# --- AC: manual similarity query sane ----------------------------------------------
def test_bm25_similarity_query_sane(ingested):
    """Topical sanity only. BM25 alone cannot disambiguate entities shared
    across doc types (e.g. a 1099 payer that is also an invoice client) —
    observed here and recorded in PROGRESS.md; that is Phase 4's job."""
    bm25 = Bm25Index.load(ingested["index_dir"] / "bm25.json")
    by_id = {c.chunk_id: c for c in ingested["chunks"]}
    gt = ingested["gt"]

    hits = bm25.query("1099 nonemployee compensation tax year", k=3)
    types = [gt[by_id[cid].doc_id]["doc_type"] for cid, _ in hits]
    assert types.count("form_1099") == 3, types

    hits = bm25.query("Blue Bottle Coffee", k=3)
    top_types = [gt[by_id[cid].doc_id]["doc_type"] for cid, _ in hits]
    assert top_types[0] == "bank_statement", top_types  # merchant only on statements


def test_vector_similarity_query_sane(ingested):
    cfg = ingested["cfg"]
    embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
    if not embedder.is_available():
        pytest.skip("Ollama or the embedding model is unavailable (CI)")

    index = VectorIndex(ingested["index_dir"] / "chroma", embedder)
    index.build(ingested["chunks"])

    by_id = {c.chunk_id: c for c in ingested["chunks"]}
    gt = ingested["gt"]

    hits = index.query("What was the closing balance on my bank statement in March?", k=3)
    types = [gt[by_id[cid].doc_id]["doc_type"] for cid, _ in hits]
    assert types.count("bank_statement") >= 2, types

    hits = index.query("earnings statement showing net pay and deductions", k=3)
    types = [gt[by_id[cid].doc_id]["doc_type"] for cid, _ in hits]
    assert types.count("pay_stub") >= 2, types
