"""Manifest-backed metric regression comparisons."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from vaultledger.schemas import RunManifest

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "regression_baseline.json"


class MetricPolicy(BaseModel):
    baseline: float
    max_drop: float = Field(ge=0)
    higher_is_better: bool = True


class RegressionBaseline(BaseModel):
    version: str
    source_run_id: str
    golden_set_hash: str
    metrics: dict[str, MetricPolicy]


class MetricDelta(BaseModel):
    metric: str
    baseline: float
    current: float | None
    delta: float | None
    threshold: float
    regressed: bool
    reason: str


class RegressionReport(BaseModel):
    baseline_version: str
    baseline_run_id: str
    current_run_id: str
    passed: bool
    deltas: list[MetricDelta]


def load_baseline(path: str | Path = DEFAULT_BASELINE_PATH) -> RegressionBaseline:
    return RegressionBaseline.model_validate_json(Path(path).read_text())


def compare_manifest(
    baseline: RegressionBaseline,
    current: RunManifest,
) -> RegressionReport:
    if current.golden_set_hash != baseline.golden_set_hash:
        raise ValueError("baseline and current manifest use different golden sets")
    deltas: list[MetricDelta] = []
    for name, policy in baseline.metrics.items():
        value = current.metrics.get(name)
        if value is None:
            deltas.append(
                MetricDelta(
                    metric=name,
                    baseline=policy.baseline,
                    current=None,
                    delta=None,
                    threshold=policy.max_drop,
                    regressed=True,
                    reason="required metric missing",
                )
            )
            continue
        raw_delta = value - policy.baseline
        signed_improvement = raw_delta if policy.higher_is_better else -raw_delta
        regressed = signed_improvement < -policy.max_drop
        deltas.append(
            MetricDelta(
                metric=name,
                baseline=policy.baseline,
                current=value,
                delta=raw_delta,
                threshold=policy.max_drop,
                regressed=regressed,
                reason=(
                    f"drop exceeded {policy.max_drop:.4f}"
                    if regressed
                    else "within threshold"
                ),
            )
        )
    return RegressionReport(
        baseline_version=baseline.version,
        baseline_run_id=baseline.source_run_id,
        current_run_id=current.run_id,
        passed=not any(delta.regressed for delta in deltas),
        deltas=deltas,
    )


def compare_files(
    baseline_path: str | Path,
    current_path: str | Path,
) -> RegressionReport:
    baseline = load_baseline(baseline_path)
    current = RunManifest.model_validate_json(Path(current_path).read_text())
    return compare_manifest(baseline, current)


def write_report(report: RegressionReport, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report.model_dump(), indent=2) + "\n")


__all__ = [
    "DEFAULT_BASELINE_PATH",
    "MetricDelta",
    "MetricPolicy",
    "RegressionBaseline",
    "RegressionReport",
    "compare_files",
    "compare_manifest",
    "load_baseline",
    "write_report",
]
