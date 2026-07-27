"""Phase 0 acceptance criteria as tests (SPEC.md Section 16, Phase 0).

AC: app boots; schemas import; config loads. The Streamlit boot is verified
out of band (a running server + health check); here we cover the two
deterministic ACs plus the Section 15.2 "no unbounded loops" rule so the
discipline is enforced from the very first commit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from vaultledger import load_config, schemas

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "vaultledger"


# --- AC: schemas import and instantiate --------------------------------------
def test_all_schemas_present():
    expected = {
        "DocMeta",
        "Chunk",
        "Citation",
        "RoutingDecision",
        "GuardrailEvent",
        "AgentStep",
        "Answer",
        "QAExample",
        "RunManifest",
    }
    assert expected.issubset(set(schemas.__all__))


def test_answer_round_trips_with_nested_models():
    """Answer references RoutingDecision/GuardrailEvent/AgentStep; make sure the
    nested contract validates and serializes without a forward-ref rebuild."""
    routing = schemas.RoutingDecision(
        query_id="q1",
        allowed_tiers=["T0", "T1"],
        chosen_tier="T1",
        chosen_model="ollama/qwen3:8b",
        reason="category=single_doc -> T1",
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )
    answer = schemas.Answer(
        answer_text="Your March closing balance was $4,207.55.",
        citations=[
            schemas.Citation(
                chunk_id="c1",
                doc_id="stmt_march",
                page=1,
                snippet="Closing balance $4,207.55",
            )
        ],
        confidence=0.9,
        model_used="ollama/qwen3:8b",
        tier="T1",
        variant="B_hybrid",
        privacy_mode="local",
        data_left_machine=False,
        routing=routing,
    )
    dumped = answer.model_dump()
    assert dumped["data_left_machine"] is False
    assert dumped["routing"]["chosen_tier"] == "T1"
    assert schemas.Answer.model_validate(dumped).confidence == 0.9


def test_confidence_bounds_enforced():
    routing = schemas.RoutingDecision(
        query_id="q",
        allowed_tiers=["T1"],
        chosen_tier="T1",
        chosen_model="m",
        reason="r",
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )
    with pytest.raises(ValidationError):
        schemas.Answer(
            answer_text="x",
            confidence=1.5,  # out of [0, 1]
            model_used="m",
            tier="T1",
            variant="A_naive",
            privacy_mode="local",
            data_left_machine=False,
            routing=routing,
        )


def test_qa_example_category_is_constrained():
    ok = schemas.QAExample(
        id="g1",
        question="What was my closing balance on the March statement?",
        expected_answer="$4,207.55",
        expected_doc_ids=["stmt_march"],
        expected_snippets=["Closing balance $4,207.55"],
        category="single_doc",
        difficulty="easy",
    )
    assert ok.expected_tier is None
    with pytest.raises(ValidationError):
        schemas.QAExample(
            id="g2",
            question="?",
            expected_answer="",
            expected_doc_ids=[],
            expected_snippets=[],
            category="not_a_real_category",
            difficulty="easy",
        )


# --- AC: config loads --------------------------------------------------------
def test_config_loads_expected_values():
    cfg = load_config()
    assert cfg.seed == 42
    assert cfg.budgets.project_usd == 40.00
    assert cfg.loops.agent_steps_max == 6
    assert cfg.thresholds.over_refusal_max == 0.05
    assert cfg.models.T1.id.startswith("ollama/")
    assert len(cfg.models.T2) >= 2  # open-weight hosted candidates
    assert cfg.variant_default == "B_hybrid"
    assert cfg.reranker.model == "BAAI/bge-reranker-base"
    assert cfg.retrieval.rrf_constant == 60
    assert cfg.retrieval.answer_top_n == 6


# --- SPEC 15.2: no unbounded loops in the package ----------------------------
def test_no_unbounded_while_true():
    offenders = []
    for py in PACKAGE_DIR.rglob("*.py"):
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if re.search(r"while\s+True", line):
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{i}")
    assert not offenders, f"Unbounded loops found (SPEC 15.2): {offenders}"
