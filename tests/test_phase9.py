"""Phase 9 judge-validation and regression-runner gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vaultledger.evals.judge import (
    JudgeVerdict,
    load_human_labels,
    rubric_hash,
    validation_metrics,
)
from vaultledger.evals.regression import (
    RegressionBaseline,
    compare_manifest,
    load_baseline,
)
from vaultledger.schemas import RunManifest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _manifest(metrics: dict[str, float]) -> RunManifest:
    baseline = load_baseline()
    return RunManifest(
        run_id="current",
        timestamp="2026-07-28T00:00:00Z",
        git_sha="abc",
        config_hash="cfg",
        golden_set_hash=baseline.golden_set_hash,
        seed=42,
        variant="B_hybrid",
        model="fixture",
        metrics=metrics,
        total_cost_usd=0.0,
        failures=[],
    )


def test_human_label_set_is_versioned_balanced_and_exactly_twenty():
    items = load_human_labels()
    assert len(items) == 20
    assert sum(item.human_pass for item in items) == 10
    assert len(rubric_hash()) == 64


def test_judge_tpr_tnr_are_computed_independently():
    items = load_human_labels()
    verdicts = {
        item.id: JudgeVerdict(
            passed=item.human_pass,
            reason="aligned fixture",
            failure_code="NONE" if item.human_pass else "INCORRECT",
        )
        for item in items
    }
    # One false negative and one false positive: both rates must show 9/10.
    positive = next(item for item in items if item.human_pass)
    negative = next(item for item in items if not item.human_pass)
    verdicts[positive.id] = JudgeVerdict(
        passed=False, reason="fixture FN", failure_code="OTHER"
    )
    verdicts[negative.id] = JudgeVerdict(
        passed=True, reason="fixture FP", failure_code="NONE"
    )
    metrics, failures = validation_metrics(items, verdicts)
    assert metrics["judge_tpr"] == 0.9
    assert metrics["judge_tnr"] == 0.9
    assert metrics["judge_accuracy"] == 0.9
    assert len(failures) == 2


def test_persisted_regression_baseline_passes_at_its_recorded_values():
    baseline = load_baseline()
    current = _manifest(
        {name: policy.baseline for name, policy in baseline.metrics.items()}
    )
    report = compare_manifest(baseline, current)
    assert report.passed
    assert not any(delta.regressed for delta in report.deltas)


def test_regression_self_comparison_is_rejected():
    baseline = load_baseline()
    current = _manifest(
        {name: policy.baseline for name, policy in baseline.metrics.items()}
    )
    current.run_id = baseline.source_run_id

    with pytest.raises(ValueError, match="self-comparison"):
        compare_manifest(baseline, current)


def test_eval_full_regenerates_dense_and_hybrid_runs_before_regression():
    makefile = (REPO_ROOT / "Makefile").read_text()
    eval_full = makefile.split("eval-full:", 1)[1].split("verify-track-a:", 1)[0]

    dense = eval_full.index("run --variant A_naive")
    hybrid = eval_full.index("run --variant B_hybrid")
    regression = eval_full.index("evals regression")

    assert dense < hybrid < regression


def test_regression_runner_catches_deliberately_injected_drop():
    baseline = load_baseline()
    metrics = {name: policy.baseline for name, policy in baseline.metrics.items()}
    metrics["retrieval_mrr"] -= 0.02  # threshold is 0.01
    report = compare_manifest(baseline, _manifest(metrics))
    assert not report.passed
    failed = [delta for delta in report.deltas if delta.regressed]
    assert len(failed) == 1
    assert failed[0].metric == "retrieval_mrr"
    assert failed[0].delta == pytest.approx(-0.02)


def test_missing_required_metric_is_a_regression():
    baseline = load_baseline()
    metrics = {
        name: policy.baseline
        for name, policy in baseline.metrics.items()
        if name != "retrieval_hit_rate"
    }
    report = compare_manifest(baseline, _manifest(metrics))
    failed = next(delta for delta in report.deltas if delta.metric == "retrieval_hit_rate")
    assert not report.passed and failed.regressed
    assert failed.reason == "required metric missing"


def test_baseline_file_is_valid_json_and_self_describing():
    baseline = load_baseline()
    round_trip = RegressionBaseline.model_validate_json(
        json.dumps(baseline.model_dump())
    )
    assert round_trip.version == "phase9_retrieval_v1"
    # Pinned deliberately so the frozen reference cannot be re-pointed silently.
    # Re-pinned 2026-08-05 from phase4_de57151e3ae3 after Phase 12's
    # expected_tier relabel changed the golden-set hash. All four retrieval
    # metrics were bit-identical across the two runs, which is the only
    # condition under which moving this pin is safe. Changing it must stay a
    # reviewed edit, not a side effect.
    assert round_trip.source_run_id == "phase4_551b3b20b9f9"
