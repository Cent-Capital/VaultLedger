"""Deterministic tests for ADR-0020's zero-generation replay."""

from __future__ import annotations

import pytest

from scripts.support_coverage_replay import replay_rows
from vaultledger.schemas import QAExample


def _example(example_id: str, question: str) -> QAExample:
    return QAExample(
        id=example_id,
        question=question,
        expected_answer="expected",
        expected_doc_ids=["doc"],
        expected_snippets=[],
        category="global_summary",
        difficulty="hard",
    )


def _row(
    example_id: str,
    answer_text: str,
    snippet: str,
    *,
    judge_passed: bool,
    strict_match: bool,
) -> dict:
    return {
        "example_id": example_id,
        "category": "global_summary",
        "strict_match": strict_match,
        "judge": {"passed": judge_passed},
        "answer": {
            "answer_text": answer_text,
            "abstained": False,
            "citations": [
                {
                    "chunk_id": f"{example_id}#c0",
                    "doc_id": "doc",
                    "page": 1,
                    "snippet": snippet,
                    "corpus": "synthetic",
                    "ocr_derived": False,
                }
            ],
        },
    }


def test_replay_records_downgrade_with_stored_judge_and_strict_status():
    examples = [
        _example("bad", "Which merchants recur?"),
        _example("good", "Does Halcyon Retail Group recur?"),
    ]
    rows = [
        _row(
            "bad",
            "Halcyon Retail Group and CVS Pharmacy recur.",
            "Halcyon Retail Group recurs.",
            judge_passed=False,
            strict_match=False,
        ),
        _row(
            "good",
            "Halcyon Retail Group recurs.",
            "Halcyon Retail Group recurs.",
            judge_passed=True,
            strict_match=True,
        ),
    ]

    summary, downgraded = replay_rows(rows, examples)

    assert summary == {
        "rows": 2,
        "answered_rows": 2,
        "already_abstained_rows": 0,
        "downgraded_rows": 1,
        "false_positive_rows": 0,
    }
    assert downgraded == [
        {
            "example_id": "bad",
            "category": "global_summary",
            "unsupported_entities": ["CVS Pharmacy"],
            "judge_passed": False,
            "strict_match": False,
            "passes_both": False,
        }
    ]


def test_replay_counts_a_retracted_judge_and_strict_pass_as_false_positive():
    examples = [_example("bad", "Which merchants recur?")]
    rows = [
        _row(
            "bad",
            "Halcyon Retail Group and CVS Pharmacy recur.",
            "Halcyon Retail Group recurs.",
            judge_passed=True,
            strict_match=True,
        )
    ]

    summary, downgraded = replay_rows(rows, examples)

    assert summary["false_positive_rows"] == 1
    assert downgraded[0]["passes_both"] is True


def test_replay_fails_loud_on_duplicate_or_missing_rows():
    examples = [_example("a", "question"), _example("b", "question")]
    duplicate = _row(
        "a",
        "Halcyon Retail Group recurs.",
        "Halcyon Retail Group recurs.",
        judge_passed=True,
        strict_match=True,
    )
    with pytest.raises(ValueError, match="duplicate"):
        replay_rows([duplicate, duplicate], examples)
    with pytest.raises(ValueError, match="population mismatch"):
        replay_rows([duplicate], examples)
