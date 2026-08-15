"""Phase 19 decision index: every ADR classified, no waiver read as a success."""

from __future__ import annotations

import json

import pytest

from scripts.phase19_adr_index import (
    CLASSIFICATIONS,
    DECISIONS_DIR,
    MINIMUM_DECISIONS,
    NOT_A_SUCCESS,
    OUTCOME_ORDER,
    build_report,
    load_adrs,
    parse_adr,
)
from vaultledger.config import REPO_ROOT


def test_every_committed_adr_is_classified():
    """A new ADR must be classified, not rendered as an unqualified acceptance."""
    files = {
        int(path.name.removeprefix("ADR-")[:4])
        for path in DECISIONS_DIR.glob("ADR-0*.md")
        if path.name != "ADR-TEMPLATE.md"
    }
    assert files == set(CLASSIFICATIONS)
    assert len(files) >= MINIMUM_DECISIONS


def test_unclassified_adr_fails_the_run(tmp_path):
    adr = tmp_path / "ADR-0099-invented.md"
    adr.write_text("# ADR-0099: An invented decision\n\n2026-08-14 · Status: **accepted**\n")
    with pytest.raises(ValueError, match="no entry in CLASSIFICATIONS"):
        load_adrs(tmp_path)


def test_status_is_read_from_the_header_line_only():
    """ADR-0001 writes an unbolded status; the parse must stop at the newline."""
    _, _, _, status, _ = parse_adr(DECISIONS_DIR / "ADR-0001-baseline-stack.md")
    assert status == "accepted"
    assert "Context" not in status


def test_every_outcome_class_is_known_and_ordered():
    for classification in CLASSIFICATIONS.values():
        assert classification.outcome in OUTCOME_ORDER


def test_waivers_nulls_and_rejections_are_not_summarised_as_successes():
    text, receipt = build_report()

    assert receipt["outcomes"]["waiver"] == [10, 13]
    assert receipt["outcomes"]["null result"] == [16, 17]
    assert receipt["outcomes"]["rejected candidate"] == [19, 21, 22]
    assert receipt["outcomes"]["scope reduction"] == [3]

    expected = sum(
        1
        for classification in CLASSIFICATIONS.values()
        if classification.outcome in NOT_A_SUCCESS
    )
    assert receipt["not_a_success_count"] == expected
    assert f"**{expected} of {receipt['decision_count']}**" in text

    # Each one is restated in full, with the debt it leaves behind.
    assert "## Decisions that are not successes" in text
    assert "the fresh macOS Administrator-account install" in text
    assert "absence of evidence, not equivalence" in text
    assert "measured and missed at 73.3% against 80%" in text


def test_the_count_floor_is_reported_without_being_read_as_quality():
    text, receipt = build_report()
    assert receipt["meets_minimum"] is True
    assert "Meeting a count is not evidence that the decisions were good ones." in text


def test_preregistration_chains_are_parsed_not_asserted():
    _, receipt = build_report()
    by_number = {entry["number"]: entry for entry in receipt["decisions"]}
    assert 18 in by_number[19]["references"], "ADR-0019 applies ADR-0018"
    assert 20 in by_number[21]["references"], "ADR-0021 applies ADR-0020"
    assert 14 in by_number[17]["references"], "ADR-0017 applies ADR-0014"


def test_committed_index_matches_a_fresh_generation():
    committed = (REPO_ROOT / "reports" / "adr_index.md").read_text()
    text, receipt = build_report()

    def _strip_timestamp(body: str) -> list[str]:
        return [line for line in body.splitlines() if "generated 2026-" not in line]

    assert _strip_timestamp(committed) == _strip_timestamp(text)

    stored = json.loads((REPO_ROOT / "receipts" / "phase19_adr_index.json").read_text())
    assert stored["decisions"] == receipt["decisions"]
    for entry in receipt["decisions"]:
        assert len(entry["sha256"]) == 64
