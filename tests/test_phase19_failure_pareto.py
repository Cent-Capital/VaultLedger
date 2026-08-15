"""Phase 19 failure-taxonomy Pareto: the trend must be computed, not chosen."""

from __future__ import annotations

import json

from vaultledger.config import REPO_ROOT, load_config
from vaultledger.evals.failure_pareto import (
    MIN_SEQUENCE,
    Group,
    Snapshot,
    build_report,
    collect_groups,
    sequence_verdict,
)


def _snapshot(run_id: str, timestamp: str, config_hash: str, **counts: int) -> Snapshot:
    return Snapshot(
        run_id=run_id,
        relative_path=f"reports/{run_id}.json",
        timestamp=timestamp,
        config_hash=config_hash,
        rows=80,
        counts={code: value for code, value in counts.items() if value},
    )


def _group(*snapshots: Snapshot) -> Group:
    return Group(
        variant="B_hybrid",
        model="ollama/qwen3:8b",
        rows=80,
        golden_set_hash="g" * 64,
        all_snapshots=list(snapshots),
        snapshots=list(snapshots),
    )


def test_verdict_reports_a_genuine_shrink_as_shrinking():
    group = _group(
        _snapshot("a", "2026-08-01T00:00:00+00:00", "c1", ABSTAIN_FP=20, NUM_MISMATCH=10),
        _snapshot("b", "2026-08-02T00:00:00+00:00", "c2", ABSTAIN_FP=15, NUM_MISMATCH=8),
        _snapshot("c", "2026-08-03T00:00:00+00:00", "c3", ABSTAIN_FP=9, NUM_MISMATCH=5),
    )
    verdict = sequence_verdict(group)
    assert verdict["monotonic_decrease"] is True
    assert verdict["net_decrease"] is True
    assert verdict["growing_codes"] == []


def test_verdict_refuses_to_call_a_flat_then_down_sequence_shrinking():
    """48 → 48 → 47 is a net decrease. It is not bars shrinking at every step."""
    group = _group(
        _snapshot("a", "2026-08-01T00:00:00+00:00", "c1", ABSTAIN_FP=16, NUM_MISMATCH=32),
        _snapshot("b", "2026-08-02T00:00:00+00:00", "c2", ABSTAIN_FP=17, NUM_MISMATCH=31),
        _snapshot("c", "2026-08-03T00:00:00+00:00", "c3", ABSTAIN_FP=19, NUM_MISMATCH=28),
    )
    verdict = sequence_verdict(group)
    assert verdict["monotonic_decrease"] is False
    assert verdict["net_decrease"] is True
    assert verdict["growing_codes"] == ["ABSTAIN_FP"]


def test_verdict_names_a_rising_total_as_unsupported():
    group = _group(
        _snapshot("a", "2026-08-01T00:00:00+00:00", "c1", ABSTAIN_FP=33),
        _snapshot("b", "2026-08-02T00:00:00+00:00", "c2", ABSTAIN_FP=34),
        _snapshot("c", "2026-08-03T00:00:00+00:00", "c3", ABSTAIN_FP=40),
    )
    verdict = sequence_verdict(group)
    assert verdict["monotonic_decrease"] is False
    assert verdict["net_decrease"] is False
    assert verdict["total_change"] == 7


def test_discovery_excludes_rejected_candidates_and_the_decoding_sweep():
    cfg = load_config()
    groups, exclusions = collect_groups(
        shipped_temperature=cfg.generation.temperature,
        shipped_top_p=cfg.generation.top_p,
    )
    reasons = {run_id: reason for run_id, _, reason in exclusions}
    assert "phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9" in reasons
    assert "ADR-0019" in reasons["phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9"]
    adr0022_run = "matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_861c711def89"
    assert adr0022_run in reasons
    assert "ADR-0022" in reasons[adr0022_run]
    adr0023_runs = {
        "matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_6a82bd327b6e",
        "matrix_ollama_qwen3_8b_d_agentic_t0_p0p95_a4da2769451b",
    }
    assert adr0023_runs <= reasons.keys()
    assert all("ADR-0024" in reasons[run_id] for run_id in adr0023_runs)
    sweep = [run_id for run_id, reason in reasons.items() if "decoding sweep" in reason]
    assert len(sweep) == 6, "all six non-default decoding arms must be excluded"

    drawn = [group for group in groups if group.is_sequence]
    assert drawn, "the repository does contain at least one comparable sequence"
    for group in drawn:
        assert len(group.snapshots) >= MIN_SEQUENCE
        configs = [snapshot.config_hash for snapshot in group.snapshots]
        assert len(configs) == len(set(configs)), "one snapshot per pipeline config"
        timestamps = [snapshot.timestamp for snapshot in group.snapshots]
        assert timestamps == sorted(timestamps)


def test_every_group_shares_one_population_and_golden_set():
    cfg = load_config()
    groups, _ = collect_groups(
        shipped_temperature=cfg.generation.temperature,
        shipped_top_p=cfg.generation.top_p,
    )
    for group in groups:
        assert {snapshot.rows for snapshot in group.all_snapshots} == {group.rows}


def test_report_states_the_measured_verdict_for_the_shipped_arm():
    text, receipt = build_report()
    shipped = receipt["sequences"]["b_hybrid_ollama_qwen3_8b_80"]
    assert shipped["verdict"]["totals"] == [48, 48, 47]
    assert shipped["verdict"]["monotonic_decrease"] is False
    assert shipped["verdict"]["growing_codes"] == ["ABSTAIN_FP"]
    assert "not a shrinking-bars sequence" in text

    four_b = receipt["sequences"]["b_hybrid_ollama_qwen3_4b_80"]
    assert four_b["verdict"]["net_decrease"] is False
    assert "the requested shrinking-bars story is not supported" in text

    for entry in shipped["snapshots"]:
        assert len(entry["sha256"]) == 64
        assert entry["rows"] == 80


def test_charts_and_report_are_regenerated_identically():
    committed = (REPO_ROOT / "reports" / "failure_pareto.md").read_text()
    text, receipt = build_report()

    def _strip_timestamp(body: str) -> list[str]:
        return [line for line in body.splitlines() if "generated 2026-" not in line]

    assert _strip_timestamp(committed) == _strip_timestamp(text)
    for entry in receipt["sequences"].values():
        assert (REPO_ROOT / entry["chart"]).exists()

    stored = json.loads((REPO_ROOT / "receipts" / "phase19_failure_pareto.json").read_text())
    assert stored["sequences"] == receipt["sequences"]
    assert stored["coverage"] == receipt["coverage"]
