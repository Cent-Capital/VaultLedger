"""Phase 11 deterministic gateway and matrix tests."""

from __future__ import annotations

import json
from pathlib import Path

from vaultledger.evals.golden import load_golden_set
from vaultledger.evals.matrix import strict_answer_match, write_matrix_report
from vaultledger.gateway import LiteLLMGenerator
from vaultledger.schemas import Answer, RoutingDecision, RunManifest


def _answer(text: str, *, abstained: bool = False) -> Answer:
    routing = RoutingDecision(
        query_id="q_test",
        allowed_tiers=["T1"],
        chosen_tier="T1",
        chosen_model="ollama/qwen3:8b",
        reason="test",
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )
    return Answer(
        answer_text=text,
        abstained=abstained,
        confidence=0.0,
        model_used="ollama/qwen3:8b",
        tier="T1",
        variant="B_hybrid",
        privacy_mode="local",
        data_left_machine=False,
        routing=routing,
    )


def test_litellm_gateway_preserves_protocol_and_records_provider_usage():
    seen = {}

    def completion(**kwargs):
        seen.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 9},
            "_hidden_params": {"response_cost": 0.0},
        }

    generator = LiteLLMGenerator(
        "ollama/qwen3:4b",
        completion_fn=completion,
    )
    raw = generator.generate_json("prompt", {"type": "object"})

    assert json.loads(raw) == {"ok": True}
    assert seen["model"] == "ollama/qwen3:4b"
    assert seen["think"] is False
    assert seen["response_format"]["type"] == "json_schema"
    assert generator.snapshot().input_tokens == 123
    assert generator.snapshot().output_tokens == 9
    assert generator.calls[0].token_source == "provider_usage"
    assert generator.calls[0].pricing_status == "unpriced"


def test_strict_matrix_scorer_is_explicit_about_literal_matching():
    examples = {example.id: example for example in load_golden_set().examples}
    matched, reason = strict_answer_match(
        examples["sd_001"], _answer("The closing balance was $4,207.55.")
    )
    assert matched
    assert "literal anchor" in reason

    matched, reason = strict_answer_match(
        examples["sd_001"], _answer("The closing balance was $4,208.55.")
    )
    assert not matched
    assert "$4,207.55" in reason

    matched, _ = strict_answer_match(
        examples["ua_001"], _answer("I couldn't find that in your documents.", abstained=True)
    )
    assert matched


def _manifest(run_id: str, model: str) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        timestamp="2026-08-05T00:00:00+00:00",
        git_sha="abc123",
        config_hash="config",
        golden_set_hash="golden",
        seed=42,
        variant="B_hybrid",
        model=model,
        metrics={
            "matrix_examples": 2.0,
            "generation_eval_coverage": 1.0,
            "strict_answer_match_rate": 0.5,
            "citation_doc_hit_rate": 0.5,
            "abstention_accuracy": 1.0,
            "median_gateway_latency_ms": 125.0,
            "p95_gateway_latency_ms": 150.0,
            "gateway_calls": 2.0,
            "input_tokens": 200.0,
            "output_tokens": 20.0,
            "provider_token_usage_rate": 1.0,
            "model_unpriced": 1.0,
        },
        total_cost_usd=0.0,
        failures=[],
    )


def test_matrix_report_is_generated_only_from_manifest_receipts(tmp_path: Path):
    paths = []
    for manifest in (
        _manifest("phase11_qwen4", "ollama/qwen3:4b"),
        _manifest("phase11_qwen8", "ollama/qwen3:8b"),
    ):
        path = tmp_path / f"{manifest.run_id}.json"
        path.write_text(manifest.model_dump_json())
        paths.append(path)

    output = tmp_path / "model_matrix.md"
    write_matrix_report(paths, output)
    report = output.read_text()

    assert "phase11_qwen4" in report and "phase11_qwen8" in report
    assert "50.0%" in report
    assert "unpriced, not free" in report
    assert "generated, never hand-edited" in report


def test_privacy_badge_is_derived_from_the_answer_not_asserted():
    """The egress badge must read `data_left_machine`, never hardcode the claim.

    ADR-0003 retired the paid tiers, so today this always resolves to the
    "stayed on your machine" branch. That is exactly why the guard exists: a
    badge that prints the guarantee instead of deriving it would keep printing
    it after a future change re-enables a remote path, and nothing would fail.
    """
    app_source = (Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py").read_text()

    badge = "Data stayed on your machine · NO cloud egress"
    assert badge in app_source

    guard = "if answer.data_left_machine:"
    assert guard in app_source, "egress badge must branch on answer.data_left_machine"
    assert app_source.index(guard) < app_source.index(badge), (
        "the data_left_machine check must precede the success badge, so the "
        "badge is a consequence of the answer rather than an assertion about it"
    )
