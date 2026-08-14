"""Phase 19 variant-matrix generator: honesty gates and population boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vaultledger.config import REPO_ROOT
from vaultledger.evals import variant_matrix
from vaultledger.evals.variant_matrix import (
    GENERATION_POPULATIONS,
    REJECTED_CANDIDATE_RUN_ID,
    RETRIEVAL_ARMS,
    _assert_product_prompt,
    _load_manifest,
    build_report,
    reproduction_count,
)
from vaultledger.generate.reliable import PROMPT_SHA256
from vaultledger.schemas import RunManifest


def _manifest(**overrides) -> RunManifest:
    base = {
        "run_id": "test_run",
        "timestamp": "2026-08-14T00:00:00+00:00",
        "git_sha": "0" * 40,
        "config_hash": "c" * 64,
        "golden_set_hash": "g" * 64,
        "seed": 42,
        "variant": "B_hybrid",
        "model": "ollama/qwen3:8b",
        "metrics": {"matrix_examples": 80.0},
        "total_cost_usd": 0.0,
        "failures": [],
    }
    base.update(overrides)
    return RunManifest.model_validate(base)


def test_rejected_candidate_is_refused_by_name():
    """ADR-0019's candidate has better abstention numbers and must stay out."""
    candidate = _manifest(
        run_id=REJECTED_CANDIDATE_RUN_ID,
        prompt_sha256="74e412c449c53dcd701f" + "0" * 44,
    )
    with pytest.raises(ValueError, match="rejected evidence-first candidate"):
        _assert_product_prompt(candidate)


def test_any_foreign_prompt_is_refused():
    with pytest.raises(ValueError, match="not the shipped prompt"):
        _assert_product_prompt(_manifest(prompt_sha256="f" * 64))


def test_shipped_and_pre_plumbing_prompts_are_accepted():
    _assert_product_prompt(_manifest(prompt_sha256=None))
    _assert_product_prompt(_manifest(prompt_sha256=PROMPT_SHA256))


def test_declared_sources_must_be_committed():
    with pytest.raises(FileNotFoundError, match="not committed"):
        _load_manifest("reports/not_a_real_receipt.json", set())


def test_every_declared_arm_is_committed_and_carries_its_answers():
    """A declaration that names a missing or uncommitted receipt fails loudly."""
    committed = variant_matrix._committed_paths()
    for arm in RETRIEVAL_ARMS:
        assert arm.relative_path in committed
    for population in GENERATION_POPULATIONS:
        for arm in population.arms:
            assert arm.relative_path in committed
            answers = REPO_ROOT / arm.relative_path.replace(".json", "_answers.json")
            assert answers.exists(), f"{arm.label} has no committed answer receipt"


def test_reproduction_count_deduplicates_pointer_copies():
    """`phase4_latest.json` is a byte copy of a dated manifest, not a second run."""
    committed = variant_matrix._committed_paths()
    shipped = _load_manifest("reports/phase4_1966922cebd9.json", committed)
    reproducing, comparable = reproduction_count(shipped, committed)
    files = [
        path
        for path in committed
        if Path(path).name.startswith("phase4_")
        and path.endswith(".json")
        and not path.endswith(("_answer.json", "_answers.json"))
    ]
    assert comparable < len(files), "pointer copies must not inflate the run count"
    assert reproducing == comparable
    assert reproducing >= 3


def test_report_states_populations_and_never_flattens_them():
    text, receipt = build_report()

    # Each population is announced with its own row count.
    assert "70 of 80" in text
    for population in GENERATION_POPULATIONS:
        assert population.title in text

    # The unmeasured cells are named rather than left as silent blanks.
    assert "Cells that were never measured" in text
    assert "A is a retrieval baseline only" in text

    # The rejected candidate never appears, in any table or footnote.
    assert REJECTED_CANDIDATE_RUN_ID not in text
    assert receipt["rejected_run_ids"] == [REJECTED_CANDIDATE_RUN_ID]

    # Provenance is machine-checkable.
    assert receipt["product_prompt_sha256"] == PROMPT_SHA256
    assert receipt["retrieval_scored_rows"] == 70
    assert receipt["golden_examples"] == 80
    for entry in receipt["sources"].values():
        assert len(entry["sha256"]) == 64


def test_generation_arms_agree_with_the_phase_14_baseline_report():
    """The offline rescore must reproduce the separately generated Phase 14 tables."""
    text, _ = build_report()
    agentic = next(p for p in GENERATION_POPULATIONS if p.key == "agentic_targets")
    assert agentic.categories == ("aggregation", "multi_hop")

    # Values independently published in reports/phase14_agentic_matrix.md.
    assert "| D_agentic · qwen3:8b | `aggregation` | 14 | 57.1% | 66.7% (n=12) | 71.4% |" in text
    assert "| D_agentic · qwen3:4b | `multi_hop` | 12 | 8.3% | 8.3% (n=12) | 8.3% |" in text
    # Value independently published in reports/phase14_baseline_by_category.md.
    assert "| B_hybrid · qwen3:8b | `aggregation` | 14 | 14.3% | 16.7% (n=12) |" in text


def test_committed_report_matches_a_fresh_generation():
    """The checked-in report must be generated output, never a hand-edit."""
    committed = (REPO_ROOT / "reports" / "variant_matrix.md").read_text()
    text, _ = build_report()

    def _strip_timestamp(body: str) -> list[str]:
        return [line for line in body.splitlines() if "generated 2026-" not in line]

    assert _strip_timestamp(committed) == _strip_timestamp(text)


def test_committed_receipt_matches_a_fresh_generation():
    stored = json.loads((REPO_ROOT / "receipts" / "phase19_variant_matrix.json").read_text())
    _, receipt = build_report()
    for key in ("sources", "populations", "product_prompt_sha256", "golden_set_hash"):
        assert stored[key] == receipt[key]
