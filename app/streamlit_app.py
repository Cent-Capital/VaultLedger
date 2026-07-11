"""VaultLedger UI shell (SPEC.md Section 6).

Phase 0: the four screens exist and the app boots. Each screen is a labelled
placeholder wired to nothing yet; later phases fill them in. Booting this and
seeing the config values proves the config loader works end-to-end in the app.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

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
    f"Build {__version__} · Phase 0 (scaffold)."
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
    st.info("Phase 2: drag-drop upload, parsed-document table, per-index rebuild.")

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
