"""Phase 12 deterministic policy, budget, escalation, and label gates."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from vaultledger.evals.golden import load_golden_set
from vaultledger.evals.router import POLICIES, _best_receipt, evaluate_policies
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.route import BudgetExhausted, PolicyRouter, answer_with_policy
from vaultledger.schemas import Answer, Chunk, RoutingDecision


class _Retriever:
    variant = "B_hybrid"

    def __init__(self, score: float = 0.9) -> None:
        self.score = score

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        text = "The March closing balance was $4,207.55."
        return [
            ScoredChunk(
                chunk=Chunk(
                    chunk_id="c0",
                    doc_id="d0",
                    text=text,
                    page=1,
                    char_start=0,
                    char_end=len(text),
                ),
                score=self.score,
                rank=1,
                source="test",
            )
        ]


class _Generator:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.calls = 0

    def generate_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> str:
        self.calls += 1
        return json.dumps(self.output)


def _good() -> dict:
    return {
        "answer_text": "The balance was $4,207.55.",
        "abstained": False,
        "citations": [
            {"chunk_id": "c0", "snippet": "March closing balance was $4,207.55"}
        ],
    }


def _abstain() -> dict:
    return {
        "answer_text": "I couldn't find that in your documents.",
        "abstained": True,
        "citations": [],
    }


def _router(*, costs: dict[str, float] | None = None) -> PolicyRouter:
    return PolicyRouter(
        models={"T0": "ollama/qwen3:4b", "T1": "ollama/qwen3:8b"},
        t0_categories={"single_doc", "guardrail_benign"},
        rerank_tau=0.35,
        projected_cost_usd=costs or {"T0": 0.0, "T1": 0.0},
    )


def test_router_labels_match_the_reviewable_category_policy():
    examples = load_golden_set().examples
    assert Counter(example.expected_tier for example in examples) == {"T0": 24, "T1": 56}
    decisions = [
        _router().decide(category=example.category, remaining_budget_usd=2.0)
        for example in examples
    ]
    accuracy = sum(
        decision.chosen_tier == example.expected_tier
        for decision, example in zip(decisions, examples, strict=True)
    ) / len(examples)
    assert accuracy == 1.0
    assert all(decision.allowed_tiers == ["T0", "T1"] for decision in decisions)


def test_low_retrieval_confidence_promotes_a_simple_query_to_t1():
    decision = _router().decide(
        category="single_doc",
        retrieval_confidence=0.2,
        remaining_budget_usd=2.0,
    )
    assert decision.chosen_tier == "T1"
    assert "retrieval_confidence=0.200" in decision.reason


def test_confidence_promotion_is_not_reported_as_a_budget_cap():
    result = answer_with_policy(
        "What was the balance?",
        _Retriever(),
        {"T0": _Generator(_good()), "T1": _Generator(_good())},
        router=_router(),
        category="single_doc",
        retrieval_confidence=0.2,
        remaining_budget_usd=2.0,
    )

    assert result.answer.routing.chosen_tier == "T1"
    assert result.notice is None


def test_budget_guard_caps_or_refuses_tiers_deterministically():
    router = _router(costs={"T0": 0.1, "T1": 0.8})
    capped = router.decide(category="aggregation", remaining_budget_usd=0.5)
    assert capped.allowed_tiers == ["T0"]
    assert capped.chosen_tier == "T0"
    assert "budget=$0.500000 capped" in capped.reason

    with pytest.raises(BudgetExhausted):
        router.decide(category="single_doc", remaining_budget_usd=0.05)


def test_t0_abstention_escalates_once_to_t1_and_logs_the_final_decision():
    t0 = _Generator(_abstain())
    t1 = _Generator(_good())
    result = answer_with_policy(
        "What was the balance?",
        _Retriever(),
        {"T0": t0, "T1": t1},
        router=_router(),
        category="single_doc",
        remaining_budget_usd=2.0,
    )

    assert t0.calls == 1 and t1.calls == 1
    assert len(result.attempts) == 2
    assert result.answer.abstained is False
    assert result.answer.model_used == "ollama/qwen3:8b"
    assert result.answer.routing.chosen_tier == "T1"
    assert result.answer.routing.escalations == 1
    assert "model abstained" in result.answer.routing.reason
    assert any(event.guard == "router_escalation" for event in result.answer.guardrail_events)
    assert result.answer.privacy_mode == "local"
    assert result.answer.data_left_machine is False


def test_budget_can_block_escalation_without_exceeding_the_loop_cap():
    t0 = _Generator(_abstain())
    t1 = _Generator(_good())
    result = answer_with_policy(
        "What was the balance?",
        _Retriever(),
        {"T0": t0, "T1": t1},
        router=_router(costs={"T0": 0.1, "T1": 0.8}),
        category="single_doc",
        remaining_budget_usd=0.5,
        escalation_max=2,
    )

    assert len(result.attempts) == 1
    assert t0.calls == 1 and t1.calls == 0
    assert result.answer.abstained
    assert result.answer.routing.escalations == 0


def _receipt_row(
    example_id: str,
    *,
    tier: str,
    strict: bool,
    abstained: bool,
    confidence: float,
    latency_ms: float,
) -> dict:
    model = "ollama/qwen3:4b" if tier == "T0" else "ollama/qwen3:8b"
    decision = RoutingDecision(
        query_id=f"q_{example_id}",
        allowed_tiers=["T0", "T1"],
        chosen_tier=tier,
        chosen_model=model,
        reason="fixture",
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )
    answer = Answer(
        answer_text=(
            "I couldn't find that in your documents." if abstained else "fixture answer"
        ),
        abstained=abstained,
        confidence=confidence,
        model_used=model,
        tier=tier,
        variant="B_hybrid",
        privacy_mode="local",
        data_left_machine=False,
        routing=decision,
    )
    return {
        "example_id": example_id,
        "strict_match": strict,
        "citation_doc_hit": strict,
        "abstention_correct": strict,
        "gateway": {"latency_ms": latency_ms},
        "answer": answer.model_dump(),
    }


def test_frontier_reuses_cached_answers_across_four_distinct_policies():
    by_id = {example.id: example for example in load_golden_set().examples}
    examples = [by_id["sd_001"], by_id["ag_001"], by_id["ua_001"]]
    t0_rows = [
        _receipt_row(
            "sd_001", tier="T0", strict=False, abstained=True,
            confidence=0.0, latency_ms=3000,
        ),
        _receipt_row(
            "ag_001", tier="T0", strict=False, abstained=True,
            confidence=0.0, latency_ms=3000,
        ),
        _receipt_row(
            "ua_001", tier="T0", strict=True, abstained=True,
            confidence=0.0, latency_ms=3000,
        ),
    ]
    t1_rows = [
        _receipt_row(
            "sd_001", tier="T1", strict=True, abstained=False,
            confidence=0.9, latency_ms=5000,
        ),
        _receipt_row(
            "ag_001", tier="T1", strict=True, abstained=False,
            confidence=0.9, latency_ms=5000,
        ),
        _receipt_row(
            "ua_001", tier="T1", strict=True, abstained=True,
            confidence=0.0, latency_ms=5000,
        ),
    ]

    metrics, failures, payload = evaluate_policies(
        examples,
        t0_rows,
        t1_rows,
        router=_router(),
        remaining_budget_usd=2.0,
    )

    assert failures == []
    assert metrics["routing_accuracy"] == 1.0
    assert metrics["policy.all_t0.strict_match_rate"] == pytest.approx(1 / 3)
    assert metrics["policy.all_t1.strict_match_rate"] == 1.0
    assert metrics["policy.category_static.strict_match_rate"] == pytest.approx(2 / 3)
    assert metrics["policy.policy_router.strict_match_rate"] == 1.0
    assert metrics["policy.policy_router.escalation_rate"] == pytest.approx(1 / 3)
    assert metrics["policy.policy_router.escalation_efficacy"] == 1.0
    assert {row["policy"] for row in payload[0]["policies"]} == set(POLICIES)


def test_frontier_defaults_to_the_newest_complete_receipt(tmp_path):
    for run_id, timestamp, rows in (
        ("phase11_ollama_qwen3_8b_old", "2026-08-05T12:00:00+00:00", [{"id": 1}]),
        (
            "phase11_ollama_qwen3_8b_new",
            "2026-08-05T13:00:00+00:00",
            [{"id": 1}],
        ),
        (
            "phase11_ollama_qwen3_8b_partial",
            "2026-08-05T14:00:00+00:00",
            [],
        ),
    ):
        answers = tmp_path / f"{run_id}_answers.json"
        answers.write_text(json.dumps(rows))
        manifest = {
            "run_id": run_id,
            "timestamp": timestamp,
            "git_sha": "abc123",
            "config_hash": "config",
            "golden_set_hash": "golden",
            "seed": 42,
            "variant": "B_hybrid",
            "model": "ollama/qwen3:8b",
            "metrics": {},
            "total_cost_usd": 0.0,
            "failures": [],
        }
        (tmp_path / f"{run_id}.json").write_text(json.dumps(manifest))

    selected = _best_receipt(tmp_path, "8b")

    assert selected.name == "phase11_ollama_qwen3_8b_new_answers.json"


def test_experiment_lab_surfaces_the_generated_router_artifacts():
    source = (
        Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    ).read_text()

    assert 'cfg.repo_path("reports/routing_frontier.md")' in source
    assert 'cfg.repo_path("reports/paretos/routing_frontier.svg")' in source
    assert "No router frontier receipt yet. Run `make router-eval`." in source
