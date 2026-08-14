"""Phase 19 abstention-baseline acceptance tests."""

from __future__ import annotations

import pytest

from scripts.phase19_abstention_audit import abstention_source, audit_rows
from vaultledger.schemas import QAExample


def _example(example_id: str, category: str) -> QAExample:
    return QAExample(
        id=example_id,
        question=f"question {example_id}",
        expected_answer="expected",
        expected_doc_ids=[] if category == "unanswerable" else ["doc"],
        expected_snippets=[],
        category=category,  # type: ignore[arg-type]
        difficulty="easy",
    )


def _row(
    example_id: str,
    category: str,
    *,
    abstained: bool,
    events: list[dict] | None = None,
    judge_code: str = "NONE",
) -> dict:
    return {
        "example_id": example_id,
        "category": category,
        "answer": {
            "abstained": abstained,
            "guardrail_events": events or [],
        },
        "judge": {"failure_code": judge_code},
    }


def test_abstention_audit_separates_model_guard_and_query_causes():
    examples = [
        _example("model", "single_doc"),
        _example("guard", "aggregation"),
        _example("query", "adversarial"),
        _example("right", "single_doc"),
        _example("unknown", "unanswerable"),
    ]
    rows = [
        _row("model", "single_doc", abstained=True, judge_code="FALSE_ABSTAIN"),
        _row(
            "guard",
            "aggregation",
            abstained=True,
            events=[
                {
                    "guard": "citation_verify",
                    "action": "downgrade_to_abstain",
                    "details": "no citation",
                }
            ],
        ),
        _row(
            "query",
            "adversarial",
            abstained=True,
            events=[
                {
                    "guard": "query_injection_guard",
                    "action": "block",
                    "details": "blocked",
                }
            ],
        ),
        _row("right", "single_doc", abstained=False),
        _row("unknown", "unanswerable", abstained=True),
    ]

    summary, audited = audit_rows(rows, examples)

    assert summary["rows"] == 5
    assert summary["answerable_abstentions"] == 3
    assert summary["rightly_abstained_unanswerable"] == 1
    assert summary["answered_unanswerable"] == 0
    assert summary["judge_false_abstain"] == 1
    assert summary["answerable_abstention_sources"] == {
        "guard_downgrade": 1,
        "model_declared": 1,
        "query_block": 1,
    }
    assert summary["guard_downgrade_breakdown"] == {"citation_verify": 1}
    assert [row["source"] for row in audited] == [
        "model_declared",
        "guard_downgrade",
        "query_block",
    ]


def test_abstention_source_returns_none_for_an_answer():
    assert abstention_source(_row("ok", "single_doc", abstained=False)) is None


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ([_row("a", "single_doc", abstained=True)] * 2, "duplicate answer rows"),
        ([], "population mismatch"),
    ],
)
def test_abstention_audit_fails_loud_on_bad_population(rows: list[dict], match: str):
    with pytest.raises(ValueError, match=match):
        audit_rows(rows, [_example("a", "single_doc")])
