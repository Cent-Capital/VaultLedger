"""Phase 11 deterministic gateway and matrix tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from vaultledger.config import CONFIG_PATH
from vaultledger.evals.golden import load_golden_set
from vaultledger.evals.matrix import (
    category_metrics,
    numeric_exact_match,
    score_answer,
    strict_answer_match,
    write_matrix_report,
)
from vaultledger.gateway import LiteLLMGenerator
from vaultledger.generate.ollama import OllamaGenerator
from vaultledger.schemas import Answer, QAExample, RoutingDecision, RunManifest


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
    assert seen["temperature"] == 0.0
    assert seen["top_p"] == 0.95
    assert seen["seed"] == 42
    assert seen["response_format"]["type"] == "json_schema"
    assert generator.snapshot().input_tokens == 123
    assert generator.snapshot().output_tokens == 9
    assert generator.calls[0].token_source == "provider_usage"
    assert generator.calls[0].pricing_status == "unpriced"


def test_product_and_matrix_use_the_same_native_chat_payload(monkeypatch):
    sent: list[tuple[str, dict]] = []

    class _Response:
        def raise_for_status(self) -> None: ...

        @staticmethod
        def json() -> dict:
            return {
                "message": {"content": '{"ok":true}'},
                "prompt_eval_count": 7,
                "eval_count": 3,
            }

    def fake_post(url: str, json: dict, timeout: int):  # noqa: A002
        sent.append((url, json))
        return _Response()

    monkeypatch.setattr("vaultledger.generate.ollama.requests.post", fake_post)
    settings = {
        "temperature": 0.3,
        "top_p": 0.9,
        "seed": 42,
        "num_ctx": 32768,
    }
    product = OllamaGenerator("ollama/qwen3:8b", **settings)
    matrix = LiteLLMGenerator("ollama/qwen3:8b", **settings)

    assert json.loads(product.generate_json("prompt", {"type": "object"})) == {
        "ok": True
    }
    assert json.loads(matrix.generate_json("prompt", {"type": "object"})) == {
        "ok": True
    }
    assert [url for url, _ in sent] == [
        "http://localhost:11434/api/chat",
        "http://localhost:11434/api/chat",
    ]
    assert sent[0][1] == sent[1][1]
    assert sent[0][1]["messages"] == [{"role": "user", "content": "prompt"}]
    assert sent[0][1]["options"] == {
        "temperature": 0.3,
        "top_p": 0.9,
        "seed": 42,
        "num_ctx": 32768,
    }
    assert matrix.snapshot().input_tokens == 7
    assert matrix.snapshot().output_tokens == 3


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


def _example(
    example_id: str,
    category: str,
    expected_answer: str,
) -> QAExample:
    return QAExample(
        id=example_id,
        question="q",
        expected_answer=expected_answer,
        expected_doc_ids=[],
        expected_snippets=[],
        category=category,  # type: ignore[arg-type]
        difficulty="easy",
    )


def test_numeric_exact_match_compares_parsed_numbers_not_normalized_strings():
    """The distinction that makes this a separate metric from `strict_match`.

    Phase 14's AC names *numeric* exact-match. `strict_answer_match` compares
    literal strings after normalization, so an answer that is numerically correct
    but formatted differently scores as a miss. If the two metrics agreed here
    there would be no reason to add one, and the AC could simply have been
    restated against the scorer that already existed.
    """
    example = _example("ag_x", "aggregation", "The total was $1,234.50.")
    candidate = _answer("The total was 1234.5 dollars.")

    assert strict_answer_match(example, candidate)[0] is False
    matched, reason = numeric_exact_match(example, candidate, epsilon=0.01)
    assert matched is True
    assert "matched 1" in reason


def test_numeric_exact_match_reports_the_quantity_that_is_missing():
    example = _example("ag_y", "aggregation", "$12,000.00 plus $8,500.00.")
    matched, reason = numeric_exact_match(
        example, _answer("It was $12,000.00."), epsilon=0.01
    )
    assert matched is False
    assert "8,500.00" in reason


def test_numeric_exact_match_holds_rows_without_quantities_out_of_scope():
    """Out of scope is `None`, never `False`.

    Scoring a row that has no number to reproduce as a numeric *failure* would
    understate every model on this corpus, and the understatement would be
    invisible because it lands in the same denominator as real misses.
    """
    no_quantity = _example("ag_z", "aggregation", "Halcyon Retail Group and Cedar Grove Media.")
    matched, reason = numeric_exact_match(
        no_quantity, _answer("Halcyon and Cedar Grove."), epsilon=0.01
    )
    assert matched is None
    assert "out of scope" in reason

    # `unanswerable` is out of scope even when the reference mentions a figure;
    # declining correctly is what `abstention_accuracy` measures.
    unanswerable = _example("ua_z", "unanswerable", "Not in the documents; no $5.00 figure exists.")
    matched, _ = numeric_exact_match(
        unanswerable, _answer("I can't find that.", abstained=True), epsilon=0.01
    )
    assert matched is None


def test_bare_integers_are_not_treated_as_quantities():
    """`1099` is a form, `2026` is a year, neither is a measurable quantity.

    Requiring them would put rows in scope that carry no number worth checking,
    and would credit a match for repeating the form name back.
    """
    example = _example("mh_x", "multi_hop", "Yes. The 1099 amount is $8,500.00.")
    matched, _ = numeric_exact_match(example, _answer("The figure is $8,500.00."), epsilon=0.01)
    assert matched is True

    form_only = _example("mh_y", "multi_hop", "It came from the 1099 filed in 2026.")
    assert numeric_exact_match(form_only, _answer("From the 1099."), epsilon=0.01)[0] is None


def test_abstaining_on_a_numeric_row_is_a_miss_not_an_exemption():
    example = _example("ag_w", "aggregation", "$48,461.52")
    matched, reason = numeric_exact_match(
        example, _answer("I couldn't determine that.", abstained=True), epsilon=0.01
    )
    assert matched is False
    assert "abstained" in reason


def test_category_denominators_come_from_examples_so_failed_rows_stay_misses():
    """A row that never produced an `Answer` must not shrink its category.

    This mirrors the aggregate convention. If errored rows shrank the
    denominator, a model that crashed on its hardest questions would score
    *higher* than one that answered them badly.
    """
    examples = [
        _example("ag_1", "aggregation", "$100.00"),
        _example("ag_2", "aggregation", "$200.00"),
        _example("sd_1", "single_doc", "$300.00"),
    ]
    rows = [
        {**score_answer(examples[0], _answer("$100.00"), numeric_epsilon=0.01),
         "example_id": "ag_1"},
        {"example_id": "ag_2", "category": "aggregation", "error": "boom"},
        {**score_answer(examples[2], _answer("$999.99"), numeric_epsilon=0.01),
         "example_id": "sd_1"},
    ]

    metrics = category_metrics(examples, rows)

    assert metrics["matrix_examples__aggregation"] == 2.0
    assert metrics["strict_answer_match_rate__aggregation"] == 0.5
    assert metrics["numeric_exact_match_examples__aggregation"] == 2.0
    assert metrics["numeric_exact_match_rate__aggregation"] == 0.5
    assert metrics["numeric_exact_match_rate__single_doc"] == 0.0


def test_out_of_scope_categories_omit_the_rate_rather_than_reporting_zero():
    """`metrics` is dict[str, float] and cannot hold "not applicable".

    A stored `0.0` is indistinguishable from a measured total failure, which is
    precisely how this repo's withdrawn claims drifted. Absence is the honest
    encoding; the report renders it as an em dash.
    """
    examples = [_example("gs_1", "global_summary", "Three employers, no figures given.")]
    rows = [
        {**score_answer(examples[0], _answer("Three employers."), numeric_epsilon=0.01),
         "example_id": "gs_1"}
    ]

    metrics = category_metrics(examples, rows)

    assert metrics["numeric_exact_match_examples__global_summary"] == 0.0
    assert "numeric_exact_match_rate__global_summary" not in metrics


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
    assert "Wall p50" in report
    assert "Context k" in report
    assert "retrieval-side embedding" in report
    assert "not necessarily independent signals" in report
    # Latency excludes failed rows while rates do not; an undisclosed asymmetry
    # produced a wrong tail explanation in the Phase-15 write-up.
    assert "computed over completed rows" in report
    assert "understates its observed worst case" in report


def test_matrix_report_recovers_legacy_context_only_from_matching_config(tmp_path: Path):
    matching = _manifest("phase11_matching", "ollama/qwen3:8b")
    matching.config_hash = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    stale = _manifest("phase11_stale", "ollama/qwen3:4b")
    paths = []
    for manifest in (matching, stale):
        path = tmp_path / f"{manifest.run_id}.json"
        path.write_text(manifest.model_dump_json())
        paths.append(path)

    output = tmp_path / "model_matrix.md"
    write_matrix_report(paths, output)
    rows = [line for line in output.read_text().splitlines() if line.startswith("| `ollama")]
    assert any("| `B_hybrid` | 6 |" in row for row in rows)
    assert any("| `B_hybrid` | — |" in row for row in rows)


def test_report_renders_categories_and_never_back_fills_a_missing_metric(tmp_path: Path):
    """A manifest predating a metric must show an em dash, not 0%.

    Every committed pre-Phase-14 manifest lacks the numeric and per-category keys.
    Rendering those as `0.0%` would publish a measured-looking total failure for a
    run that never computed the metric at all.
    """
    old = _manifest("phase11_old", "ollama/qwen3:4b")
    new = _manifest("phase11_new", "ollama/qwen3:8b")
    new.metrics.update(
        {
            "numeric_exact_match_examples": 2.0,
            "numeric_exact_match_rate": 0.5,
            "matrix_examples__aggregation": 2.0,
            "strict_answer_match_rate__aggregation": 0.5,
            "citation_doc_hit_rate__aggregation": 0.5,
            "abstention_accuracy__aggregation": 1.0,
            "numeric_exact_match_examples__aggregation": 2.0,
            "numeric_exact_match_rate__aggregation": 0.5,
            # An out-of-scope category: `n` is present, the rate key is absent.
            "matrix_examples__global_summary": 1.0,
            "strict_answer_match_rate__global_summary": 0.0,
            "citation_doc_hit_rate__global_summary": 0.0,
            "abstention_accuracy__global_summary": 1.0,
            "numeric_exact_match_examples__global_summary": 0.0,
        }
    )

    paths = []
    for manifest in (old, new):
        path = tmp_path / f"{manifest.run_id}.json"
        path.write_text(manifest.model_dump_json())
        paths.append(path)

    output = tmp_path / "model_matrix.md"
    write_matrix_report(paths, output)
    report = output.read_text()

    assert "## By category" in report
    assert "`aggregation`" in report and "`global_summary`" in report
    # The old manifest contributes no category rows and no invented zero.
    assert "phase11_old" in report
    assert "— |" in report, "an absent metric must render as an em dash"
    assert "50.0% (n=2)" in report


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
