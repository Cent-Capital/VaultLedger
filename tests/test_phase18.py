"""Phase 18 model identity, decoding, judging, and frontier acceptance tests."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from vaultledger.evals.matrix import (
    write_latency_quality_frontier,
    write_matrix_report,
)
from vaultledger.evals.run import build_parser
from vaultledger.generate import ollama as ollama_module
from vaultledger.schemas import (
    DecodingProfile,
    MatrixJudgeVerdict,
    ModelMetadata,
    RunManifest,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None: ...

    def json(self) -> dict:
        return self.payload


def test_ollama_metadata_uses_show_tags_and_loaded_resident_bytes(monkeypatch):
    def fake_post(url: str, json: dict, timeout: int):  # noqa: A002
        assert url.endswith("/api/show")
        assert json == {"model": "qwen3:8b"}
        return _Response(
            {
                "details": {
                    "family": "qwen3",
                    "parameter_size": "8.2B",
                    "quantization_level": "Q4_K_M",
                }
            }
        )

    def fake_get(url: str, timeout: int):
        if url.endswith("/api/tags"):
            return _Response(
                {
                    "models": [
                        {
                            "name": "qwen3:8b",
                            "digest": "sha256:abc",
                            "size": 5_200_000_000,
                        }
                    ]
                }
            )
        if url.endswith("/api/ps"):
            return _Response(
                {
                    "models": [
                        {
                            "name": "qwen3:8b",
                            "size": 6_100_000_000,
                            "size_vram": 6_000_000_000,
                        }
                    ]
                }
            )
        assert url.endswith("/api/version")
        return _Response({"version": "0.32.5"})

    monkeypatch.setattr(ollama_module.requests, "post", fake_post)
    monkeypatch.setattr(ollama_module.requests, "get", fake_get)
    metadata = ollama_module.ollama_model_metadata("ollama/qwen3:8b")

    assert metadata.parameter_count == "8.2B"
    assert metadata.quantization == "Q4_K_M"
    assert metadata.digest == "sha256:abc"
    assert metadata.artifact_size_bytes == 5_200_000_000
    assert metadata.resident_size_bytes == 6_100_000_000
    assert metadata.resident_size_vram_bytes == 6_000_000_000


def test_matrix_warmup_loads_without_generating_and_pins_context(monkeypatch):
    sent = {}

    def fake_post(url: str, json: dict, timeout: int):  # noqa: A002
        sent.update({"url": url, "payload": json, "timeout": timeout})
        return _Response({"done": True})

    monkeypatch.setattr(ollama_module.requests, "post", fake_post)
    ollama_module.ollama_warm_model("ollama/qwen3:14b")

    assert sent["url"].endswith("/api/generate")
    assert sent["payload"]["prompt"] == ""
    assert sent["payload"]["keep_alive"] == "10m"
    assert sent["payload"]["options"] == {
        "temperature": 0.0,
        "top_p": 0.95,
        "top_k": 20,
        "seed": 42,
        "num_ctx": 8192,
    }
    assert sent["timeout"] == 600


def test_generation_timeout_is_typed_and_shared():
    from vaultledger.config import load_config
    from vaultledger.gateway import LiteLLMGenerator
    from vaultledger.generate.ollama import OllamaGenerator

    cfg = load_config()
    settings = {
        "temperature": cfg.generation.temperature,
        "top_p": cfg.generation.top_p,
        "top_k": cfg.generation.top_k,
        "seed": cfg.seed,
        "num_ctx": cfg.generation.num_ctx,
        "max_tokens": cfg.generation.output_tokens_max,
        "timeout": cfg.generation.request_timeout_seconds,
    }
    assert OllamaGenerator("ollama/qwen3:8b", **settings).timeout == 600
    assert LiteLLMGenerator("ollama/qwen3:8b", **settings).timeout == 600
    assert OllamaGenerator("ollama/qwen3:8b", **settings).max_tokens == 768
    assert LiteLLMGenerator("ollama/qwen3:8b", **settings).max_tokens == 768
    assert OllamaGenerator("ollama/qwen3:8b", **settings).top_k == 20
    assert LiteLLMGenerator("ollama/qwen3:8b", **settings).top_k == 20


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="phase18_qwen8",
        timestamp="2026-08-12T00:00:00+00:00",
        git_sha="abc123",
        config_hash="config",
        golden_set_hash="golden",
        seed=42,
        variant="B_hybrid",
        model="ollama/qwen3:8b",
        metrics={
            "matrix_examples": 2.0,
            "generation_eval_coverage": 1.0,
            "judge_coverage_rate": 1.0,
            "judge_pass_rate": 0.5,
            "strict_answer_match_rate": 0.5,
            "numeric_exact_match_examples": 1.0,
            "numeric_exact_match_rate": 1.0,
            "citation_doc_hit_rate": 0.5,
            "abstention_accuracy": 1.0,
            "median_wall_latency_ms": 4200.0,
            "p95_wall_latency_ms": 5100.0,
            "median_gateway_latency_ms": 4000.0,
            "p95_gateway_latency_ms": 5000.0,
            "input_tokens": 200.0,
            "output_tokens": 20.0,
        },
        total_cost_usd=0.0,
        failures=[],
        decoding=DecodingProfile(
            temperature=0.0,
            top_p=0.95,
            top_k=20,
            seed=42,
            num_ctx=8192,
            max_tokens=768,
        ),
        prompt_sha256="a" * 64,
        model_metadata=ModelMetadata(
            parameter_count="8.2B",
            quantization="Q4_K_M",
            digest="sha256:full-digest",
            family="qwen3",
            artifact_size_bytes=5_200_000_000,
            resident_size_bytes=6_100_000_000,
            resident_size_vram_bytes=6_000_000_000,
            ollama_version="0.32.5",
        ),
        judge_model="ollama/qwen3:8b",
        judge_verdicts=[
            MatrixJudgeVerdict(
                example_id="sd_001",
                passed=True,
                reason="The amount agrees with the reference and citation.",
                failure_code="NONE",
            ),
            MatrixJudgeVerdict(
                example_id="ag_001",
                passed=False,
                reason="The answer omits one required invoice amount.",
                failure_code="INCORRECT",
            ),
        ],
    )


def test_phase18_report_and_frontier_are_manifest_generated(tmp_path: Path):
    manifest = _manifest()
    manifest.metrics["generation_eval_coverage"] = 0.6
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json())
    frontier = tmp_path / "model_frontier.svg"
    report = tmp_path / "model_matrix.md"

    write_latency_quality_frontier([manifest_path], frontier)
    write_matrix_report([manifest_path], report, frontier_path=frontier)

    ElementTree.parse(frontier)
    root = ElementTree.parse(frontier).getroot()
    svg = frontier.read_text()
    markdown = report.read_text()
    assert "Descriptive only — not a latency ranking" in svg
    assert "bubble area ≈ resident bytes" in svg
    assert "Latency uses completed rows only" in svg
    assert "cov 60%" in svg
    points = [element for element in root.iter() if element.attrib.get("class") == "data-point"]
    assert len(points) == 1
    view_box = [float(value) for value in root.attrib["viewBox"].split()]
    _, _, width, height = view_box
    for label in points[0].findall("{http://www.w3.org/2000/svg}text"):
        assert 0 <= float(label.attrib["x"]) <= width
        assert 0 <= float(label.attrib["y"]) <= height
    assert "sha256:full-digest" in markdown
    assert "8.2B" in markdown and "Q4_K_M" in markdown
    assert "a" * 64 in markdown
    assert "The answer omits one required invoice amount." in markdown
    assert "deterministic literal-anchor scorer, not a lower bound" in markdown
    assert "![Latency–quality frontier](model_frontier.svg)" in markdown


def test_phase18_cli_exposes_preregistered_sweep_judge_and_frontier():
    args = build_parser().parse_args(
        [
            "matrix",
            "--models",
            "ollama/qwen3:8b",
            "--decoding-sweep",
            "--judge-model",
            "ollama/qwen3:8b",
            "--frontier",
            "reports/phase18_decoding_frontier.svg",
        ]
    )
    assert args.decoding_sweep is True
    assert args.judge_model == "ollama/qwen3:8b"
    assert args.frontier.endswith("phase18_decoding_frontier.svg")
