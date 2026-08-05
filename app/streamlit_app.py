"""VaultLedger Track-A Streamlit application (SPEC.md Section 6)."""

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

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1240px;}
      [data-testid="stMetric"] {
        background: rgba(255,255,255,.78);
        border: 1px solid #d7e6e2;
        border-radius: 14px;
        padding: 14px 16px;
      }
      [data-testid="stSidebar"] {border-right: 1px solid #d7e6e2;}
      .vl-hero {
        padding: 24px 28px;
        border: 1px solid #c9e0da;
        border-radius: 18px;
        background: linear-gradient(120deg, #e8f3f0 0%, #f9fcfb 70%);
        margin-bottom: 18px;
      }
      .vl-eyebrow {
        color: #0f766e; font-size: .82rem; font-weight: 700;
        letter-spacing: .08em; text-transform: uppercase;
      }
      .vl-hero h1 {font-size: 2.35rem; margin: .25rem 0 .35rem 0;}
      .vl-hero p {font-size: 1.05rem; margin: 0; color: #365a53;}
    </style>
    <section class="vl-hero">
      <div class="vl-eyebrow">Local-first · cited · measured</div>
      <h1>🔒 VaultLedger</h1>
      <p>Ask financial documents a question without giving up control of the evidence.</p>
    </section>
    """,
    unsafe_allow_html=True,
)
st.caption(f"Track-A v{__version__} · synthetic data only · document Q&A, never advice")

with st.sidebar:
    st.success("Track A · release candidate")
    st.caption("Phases 0–10 · internship deliverable")
    st.divider()
    st.subheader("Local run config")
    st.metric("Seed", cfg.seed)
    st.metric("Project budget", f"${cfg.budgets.project_usd:,.2f}")
    st.write(f"**Default variant:** `{cfg.variant_default}`")
    st.write(f"**Reranker:** {'on' if cfg.reranker.enabled else 'off'}")
    st.divider()
    st.caption("Local capability map · ADR-0003")
    st.write(f"T0 `{cfg.models.T0.id}`")
    st.write(f"T1 `{cfg.models.T1.id}`")
    st.write("Matrix " + ", ".join(f"`{m.id}`" for m in cfg.models.matrix))
    st.divider()
    st.caption("Paid hosted tiers are retired; no cloud client is constructed or probed.")

library, ask, evals, lab = st.tabs(
    ["📚 Library / Ingest", "💬 Ask", "📊 Evals", "🧪 Experiment Lab"]
)

with library:
    st.header("Your document library")
    st.caption("A deterministic 60-document synthetic corpus. No real financial data.")
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    db_path = index_dir / "records.db"

    col_btn, col_note = st.columns([1, 3])
    with col_btn:
        rebuild = st.button("Rebuild indexes", type="primary")
    with col_note:
        st.caption("Parse → extract → PII-tag → chunk → Chroma + BM25. Local only.")
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
        st.info(
            "No ingested corpus yet. Run `make data && make ingest`, then `make doctor`, "
            "or click Rebuild after the PDFs exist."
        )
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

        st.subheader("Parsed documents")
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
    st.header("Ask your documents")
    st.caption("Variant B · dense + BM25 → reciprocal-rank fusion → local reranker")
    st.success("Privacy mode: Local · paid hosted tiers retired by ADR-0003")
    sample = st.selectbox(
        "Measured examples",
        (
            "Marcus's March closing balance",
            "Priya's total 1099 income",
            "An unanswerable credit-score question",
            "Write my own question",
        ),
        help="These come from the versioned golden set.",
    )
    sample_questions = {
        "Marcus's March closing balance": "What was Marcus Chen's March closing balance?",
        "Priya's total 1099 income": "What was Priya Raman's total 1099 income?",
        "An unanswerable credit-score question": "What is Marcus Chen's credit score?",
        "Write my own question": "",
    }
    question = st.text_input(
        "Question",
        value=sample_questions[sample],
        placeholder="What was Marcus Chen's March closing balance?",
        key=f"question_{sample}",
    )
    ask_clicked = st.button(
        "Ask",
        type="primary",
        disabled=not question.strip(),
    )

    if ask_clicked:
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
                    with st.spinner("Retrieving and answering..."):
                        routed = answer_with_privacy(
                            question,
                            retriever,
                            generator,
                            local_model=cfg.models.T1.id,
                            mode="local",
                            k=cfg.retrieval.answer_top_n,
                            max_retries=cfg.loops.repair_max,
                            min_snippet_chars=cfg.generation.min_snippet_chars,
                            trace_store=TraceStore(cfg.repo_path(cfg.paths.traces)),
                        )
                    answer = routed.answer
                    if routed.notice:
                        st.warning(routed.notice)
                    # Derived from the answer, never asserted. ADR-0003 retired the
                    # paid tiers, so this resolves to the success branch today --
                    # but the badge must keep reading the field that makes it true,
                    # or a future remote path would leave it silently lying.
                    if answer.data_left_machine:
                        st.warning(
                            "Synthetic query context left your machine: YES · "
                            f"answer model `{answer.model_used}`"
                        )
                    else:
                        st.success("Data stayed on your machine · NO cloud egress")
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
        except ModuleNotFoundError as exc:
            st.error(f"Missing local dependency `{exc.name}`. Run `make install`.")
        except (RuntimeError, FileNotFoundError, KeyError) as exc:
            st.error(str(exc))

with evals:
    st.header("Measured, not hand-waved")
    st.caption("Every headline below traces to a committed manifest or regression report.")
    phase3_path = cfg.repo_path("reports/phase3_baseline_latest.json")
    phase4_path = cfg.repo_path("reports/phase4_latest.json")
    safety_path = cfg.repo_path("reports/phase7_latest.json")
    judge_path = cfg.repo_path("reports/phase9_judge_latest.json")
    regression_path = cfg.repo_path("reports/regression_latest.json")

    if phase3_path.exists() and phase4_path.exists():
        dense = json.loads(phase3_path.read_text())["metrics"]
        hybrid = json.loads(phase4_path.read_text())["metrics"]
        st.subheader("Retrieval: dense baseline → hybrid + rerank")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Recall@20 · dense", f"{dense['retrieval_recall@20']:.4f}")
        r2.metric(
            "Recall@20 · hybrid",
            f"{hybrid['retrieval_recall@20']:.4f}",
            f"{hybrid['retrieval_recall@20'] - dense['retrieval_recall@20']:+.4f}",
        )
        r3.metric("MRR · dense", f"{dense['retrieval_mrr']:.4f}")
        r4.metric(
            "MRR · hybrid",
            f"{hybrid['retrieval_mrr']:.4f}",
            f"{hybrid['retrieval_mrr'] - dense['retrieval_mrr']:+.4f}",
        )
        st.caption("Population: 70 answerable items; 10 unanswerable items excluded.")

    st.subheader("Safety, judge, and regression gates")
    gate1, gate2, gate3, gate4 = st.columns(4)
    if safety_path.exists():
        safety = json.loads(safety_path.read_text())["metrics"]
        gate1.metric(
            "Unanswerable recall",
            f"{safety['abstention_unanswerable_recall']:.0%}",
            "10/10 cases",
        )
        gate2.metric(
            "Injection pass rate", f"{safety['injection_pass_rate']:.0%}", "1 seeded case"
        )
    if judge_path.exists():
        judge_manifest = json.loads(judge_path.read_text())
        judge_metrics = judge_manifest["metrics"]
        gate3.metric(
            "Judge TPR / TNR",
            f"{judge_metrics['judge_tpr']:.0%} / {judge_metrics['judge_tnr']:.0%}",
            "20 clear labels",
        )
    if regression_path.exists():
        regression = json.loads(regression_path.read_text())
        gate4.metric("Regression", "GREEN" if regression["passed"] else "RED")

    if regression_path.exists():
        with st.expander("Regression deltas vs frozen Phase-4 baseline"):
            st.dataframe(regression["deltas"], width="stretch", hide_index=True)

    st.subheader("Product query observability")
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

    st.subheader("Reproduce it")
    st.code("make eval-smoke", language="bash")
    st.code("make verify-track-a", language="bash")

with lab:
    st.header("Experiment Lab")
    st.info("Tracks B measurement · full 80-case local matrix + Phase 12 router frontier")
    matrix_path = cfg.repo_path("reports/model_matrix.md")
    if matrix_path.exists():
        st.markdown(matrix_path.read_text())
    else:
        st.warning("No model matrix receipt yet. Run `make matrix`.")

    router_report_path = cfg.repo_path("reports/routing_frontier.md")
    router_chart_path = cfg.repo_path("reports/paretos/routing_frontier.svg")
    if router_report_path.exists():
        st.divider()
        router_report = router_report_path.read_text().replace(
            "![Latency–quality frontier](paretos/routing_frontier.svg)", ""
        )
        st.markdown(router_report)
        if router_chart_path.exists():
            st.image(str(router_chart_path))
    else:
        st.warning("No router frontier receipt yet. Run `make router-eval`.")
    st.markdown(
        """
        **Next measured questions**

        - How do two local model families across three measured sizes compare on the full set?
        - Does the router's latency premium persist across repeated, idle-machine runs?
        - Where do GraphRAG and agentic RAG win, lose, and cost more than Variant B?

        The artifacts above cover two Qwen models, one variant, and all 80 golden rows.
        The six-model, all-variant bake-off and judged reasons remain Phase 17.
        """
    )
