"""VaultLedger UI shell (SPEC.md Section 6).

Phase 2: the Library screen shows the real ingested corpus (documents table,
PII tag counts, index stats) and can rebuild the indexes. The other screens
remain labelled placeholders until their phases land.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import streamlit as st

# Make the package importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vaultledger import __version__, load_config  # noqa: E402

st.set_page_config(page_title="VaultLedger", page_icon="🔒", layout="wide")

cfg = load_config()

st.title("🔒 VaultLedger")
st.caption(
    "Your private financial analyst that never phones home. "
    f"Build {__version__} · Phase 2 (ingestion & indexing)."
)

with st.sidebar:
    st.subheader("Run config")
    st.metric("Seed", cfg.seed)
    st.metric("Project budget", f"${cfg.budgets.project_usd:,.2f}")
    st.write(f"**Default variant:** `{cfg.variant_default}`")
    st.write(f"**Reranker:** {'on' if cfg.reranker.enabled else 'off'}")
    st.divider()
    st.caption("Tier map")
    st.write(f"T0 `{cfg.models.T0.id}`")
    st.write(f"T1 `{cfg.models.T1.id}`")
    st.write("T2 " + ", ".join(f"`{m.id}`" for m in cfg.models.T2))
    st.write(f"T3 `{cfg.models.T3.id}`")

library, ask, evals, lab = st.tabs(
    ["📚 Library / Ingest", "💬 Ask", "📊 Evals", "🧪 Experiment Lab"]
)

with library:
    st.header("Library / Ingest")
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    db_path = index_dir / "records.db"

    col_btn, col_note = st.columns([1, 3])
    with col_btn:
        rebuild = st.button("Rebuild indexes", type="primary")
    with col_note:
        st.caption(
            "Parses every PDF in the corpus: extract → SQLite → PII-tag → "
            "chunk → Chroma + BM25. Local only; nothing leaves this machine."
        )
    if rebuild:
        from vaultledger.ingest import run_ingest

        with st.spinner("Ingesting corpus (parse, extract, PII-tag, chunk, embed)…"):
            try:
                result = run_ingest(cfg)
                st.success(
                    f"Ingested {result.docs_ok} documents "
                    f"({result.docs_failed} failed), {result.chunks} chunks, "
                    f"vector index {'built' if result.embedded else 'skipped'}."
                )
            except (RuntimeError, FileNotFoundError) as exc:
                st.error(str(exc))

    if not db_path.exists():
        st.info("No ingested corpus yet — run `make data && make ingest`, or click Rebuild.")
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        docs = conn.execute(
            "SELECT doc_id, doc_type, period_start, period_end, page_count,"
            "       pii_entity_types, parse_status FROM documents ORDER BY doc_id"
        ).fetchall()
        chunks_file = index_dir / "chunks.jsonl"
        n_chunks = sum(1 for _ in open(chunks_file)) if chunks_file.exists() else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Documents", len(docs))
        m2.metric("Parse failures", sum(1 for d in docs if d["parse_status"] != "ok"))
        m3.metric("Chunks", n_chunks)
        m4.metric("Vector index", "built" if (index_dir / "chroma").exists() else "—")

        st.dataframe(
            [
                {
                    "Document": d["doc_id"],
                    "Type": d["doc_type"],
                    "Period": (
                        f"{d['period_start']} → {d['period_end']}" if d["period_start"] else ""
                    ),
                    "Pages": d["page_count"],
                    "PII tags": len(json.loads(d["pii_entity_types"])),
                    "Status": d["parse_status"],
                }
                for d in docs
            ],
            width="stretch",
            hide_index=True,
        )
        conn.close()

with ask:
    st.header("Ask")
    st.info(
        "Phase 3+: grounded answers with citation chips, the Privacy Switch, "
        "and the per-answer 'data left your machine' badge."
    )

with evals:
    st.header("Evals dashboard")
    st.info(
        "Phase 3+: retrieval before/after, faithfulness + abstention matrix, "
        "adversarial pass rates, guardrail confusion matrix, regression diff."
    )

with lab:
    st.header("Experiment Lab")
    st.info(
        "Tracks B/D: variant x model x subset runs, the model x metric x cost "
        "matrix, and the cost-quality frontier chart."
    )
