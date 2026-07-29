"""VaultLedger UI shell (SPEC.md Section 6).

Phase 4: the Ask screen runs hybrid dense + BM25 retrieval with RRF and optional
cross-encoder reranking. Variant A remains available in the eval harness as the
permanent baseline.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import os
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
    f"Build {__version__} · Phase 9 (validated judge and regression)."
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
    st.caption("Variant B: dense + BM25 → RRF → optional rerank.")
    privacy_mode = st.radio(
        "Privacy mode",
        ["Local", "Cloud-Boosted"],
        horizontal=True,
        help="Cloud-Boosted sends the retrieved question context to the configured provider.",
    )
    cloud_selected = privacy_mode == "Cloud-Boosted"
    cloud_consent = False
    if cloud_selected:
        cloud_consent = st.checkbox(
            "I consent to sending this query and retrieved context to the cloud provider "
            "for this session.",
            key="cloud_session_consent",
        )
    question = st.text_input(
        "Question",
        placeholder="What was Marcus Chen's March closing balance?",
    )
    ask_clicked = st.button(
        "Ask",
        type="primary",
        disabled=not question.strip() or (cloud_selected and not cloud_consent),
    )

    if ask_clicked:
        from vaultledger.gateway import OpenAICompatibleGenerator
        from vaultledger.generate import OllamaGenerator
        from vaultledger.index.embed import OllamaEmbedder
        from vaultledger.observability import TraceStore
        from vaultledger.retrieve import CrossEncoderReranker, HybridRetriever
        from vaultledger.route import answer_with_privacy

        try:
            embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
            if not embedder.is_available():
                st.error(
                    f"Ollama embedding model `{cfg.embedding.model}` is not available. "
                    "Start Ollama and pull the model, then rebuild the index if needed."
                )
            else:
                reranker = (
                    CrossEncoderReranker(cfg.reranker.model, cfg.reranker.batch_size)
                    if cfg.reranker.enabled
                    else None
                )
                retriever = HybridRetriever(
                    index_dir,
                    embedder,
                    candidate_k=cfg.retrieval.candidate_k,
                    rank_constant=cfg.retrieval.rrf_constant,
                    reranker=reranker,
                )
                generator = OllamaGenerator(cfg.models.T1.id, base_url=cfg.embedding.ollama_url)
                if not generator.is_available():
                    st.error(f"Generation model `{cfg.models.T1.id}` is not available in Ollama.")
                else:
                    cloud_generator = None
                    if cloud_selected and cfg.cloud.base_url:
                        api_key = os.getenv(cfg.cloud.api_key_env, "")
                        if api_key:
                            cloud_generator = OpenAICompatibleGenerator(
                                cfg.cloud.model,
                                cfg.cloud.base_url,
                                api_key,
                                cfg.cloud.timeout_seconds,
                            )
                    with st.spinner("Retrieving and answering..."):
                        routed = answer_with_privacy(
                            question,
                            retriever,
                            generator,
                            local_model=cfg.models.T1.id,
                            mode="cloud" if cloud_selected else "local",
                            cloud_consent=cloud_consent,
                            cloud_generator=cloud_generator,
                            cloud_model=cfg.cloud.model,
                            k=cfg.retrieval.answer_top_n,
                            max_retries=cfg.loops.repair_max,
                            min_snippet_chars=cfg.generation.min_snippet_chars,
                            trace_store=TraceStore(cfg.repo_path(cfg.paths.traces)),
                            input_per_million_usd=cfg.cloud.input_per_million_usd,
                            output_per_million_usd=cfg.cloud.output_per_million_usd,
                        )
                    answer = routed.answer
                    if routed.notice:
                        st.warning(routed.notice)
                    if answer.data_left_machine:
                        st.warning(
                            "Data left your machine: YES · "
                            f"cloud model `{cfg.cloud.model}` · "
                            f"answer model `{answer.model_used}`"
                        )
                    else:
                        st.success("Data left your machine: NO")
                    if answer.abstained:
                        st.warning(answer.answer_text)
                    else:
                        st.write(answer.answer_text)
                    if answer.citations:
                        st.subheader("Verified citations")
                        for c in answer.citations:
                            with st.expander(f"{c.doc_id} · page {c.page} · {c.chunk_id}"):
                                st.write(c.snippet)
                    if answer.guardrail_events:
                        with st.expander(f"Reliability events ({len(answer.guardrail_events)})"):
                            for ev in answer.guardrail_events:
                                st.caption(f"[{ev.guard}/{ev.action}] {ev.details}")
                    st.caption(
                        f"model={answer.model_used} · tier={answer.tier} · "
                        f"variant={answer.variant} · confidence={answer.confidence:.2f}"
                    )
                    if routed.trace:
                        st.caption(
                            f"trace={routed.trace.trace_id} · "
                            f"latency={routed.trace.total_latency_ms / 1000:.2f}s · "
                            f"tokens≈{routed.trace.input_tokens + routed.trace.output_tokens} "
                            f"({routed.trace.token_count_source}) · "
                            f"cost=${routed.trace.cost_usd:.6f}"
                        )
        except (RuntimeError, FileNotFoundError, KeyError) as exc:
            st.error(str(exc))

with evals:
    st.header("Evals dashboard")
    from vaultledger.observability import TraceStore, trace_rollups

    traces = TraceStore(cfg.repo_path(cfg.paths.traces)).load()
    if traces:
        rollups = trace_rollups(traces)
        health = rollups["health"]["all"]
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Queries traced", int(health["queries"]))
        h2.metric("Abstention rate", f"{health['abstention_rate']:.1%}")
        h3.metric("Repair-trigger rate", f"{health['repair_trigger_rate']:.1%}")
        h4.metric("Guardrail-flag rate", f"{health['guardrail_flag_rate']:.1%}")
        st.subheader("Cost and latency attribution")
        rows = []
        for dimension in ("feature", "category", "tier", "variant"):
            for value, metrics in rollups[dimension].items():
                rows.append(
                    {
                        "Dimension": dimension,
                        "Value": value,
                        "Queries": int(metrics["queries"]),
                        "Cost (USD)": metrics["cost_usd"],
                        "Avg latency (ms)": metrics["avg_latency_ms"],
                    }
                )
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(
            "Local inference cost is $0; token counts are explicitly estimated "
            "unless a provider returns usage."
        )
    else:
        st.info("No product query traces yet. Ask a question to populate observability.")

    judge_path = Path("reports/phase9_judge_latest.json")
    regression_path = Path("reports/regression_latest.json")
    if judge_path.exists():
        judge_manifest = json.loads(judge_path.read_text())
        judge_metrics = judge_manifest["metrics"]
        st.subheader("Judge validation")
        j1, j2, j3 = st.columns(3)
        j1.metric("TPR", f"{judge_metrics['judge_tpr']:.0%}")
        j2.metric("TNR", f"{judge_metrics['judge_tnr']:.0%}")
        j3.metric("Human labels", int(judge_metrics["judge_validation_n"]))
    if regression_path.exists():
        regression = json.loads(regression_path.read_text())
        st.subheader("Regression gate")
        if regression["passed"]:
            st.success(
                f"Green against baseline `{regression['baseline_run_id']}`"
            )
        else:
            st.error("Regression detected")
        st.dataframe(regression["deltas"], width="stretch", hide_index=True)
    st.write("Retrieval eval CLI:")
    st.code("make eval-smoke", language="bash")
    st.code(
        ".venv/bin/python -m vaultledger.evals run --variant B_hybrid", language="bash"
    )
    st.caption(
        "The dashboard visualization lands in later phases; the harness already "
        "writes RunManifest JSON under reports/."
    )

with lab:
    st.header("Experiment Lab")
    st.info(
        "Tracks B/D: variant x model x subset runs, the model x metric x cost "
        "matrix, and the cost-quality frontier chart."
    )
