"""Phase 8 full-trace, cost-attribution, and health-metric gates."""

from __future__ import annotations

import json

from vaultledger.observability import TraceStore, export_to_langfuse, trace_rollups
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.route import answer_with_privacy
from vaultledger.schemas import Chunk


class _Retriever:
    variant = "B_hybrid"

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        text = "March closing balance was $4,207.55."
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
                score=0.8,
                rank=1,
                source="hybrid",
            )
        ]


def _good() -> str:
    return json.dumps(
        {
            "answer_text": "The balance was $4,207.55.",
            "abstained": False,
            "citations": [
                {"chunk_id": "c0", "snippet": "March closing balance was $4,207.55"}
            ],
        }
    )


class _Generator:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = outputs or [_good()]
        self.calls = 0

    def generate_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> str:
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return output


def test_every_product_query_persists_full_stage_trace(tmp_path):
    store = TraceStore(tmp_path / "traces")
    routed = answer_with_privacy(
        "What was the balance?",
        _Retriever(),
        _Generator(["not json", _good()]),
        local_model="ollama/qwen3:8b",
        mode="local",
        category="single_doc",
        trace_store=store,
    )
    assert routed.trace is not None
    names = {span.name for span in routed.trace.spans}
    assert {
        "route",
        "retrieve",
        "assemble",
        "guards_in",
        "generate_repair",
        "guards_out",
    } <= names
    assert routed.trace.total_latency_ms >= 0
    assert routed.trace.input_tokens > 0
    assert routed.trace.output_tokens > 0
    assert routed.trace.token_count_source == "estimated_chars_div_4"
    assert routed.trace.cost_usd == 0.0
    assert routed.trace.repair_triggered
    assert routed.answer.routing.actual_cost_usd == 0.0
    loaded = store.load()
    assert len(loaded) == 1 and loaded[0].trace_id == routed.trace.trace_id


def test_cloud_cost_and_rollups_are_attributed_by_required_dimensions(tmp_path):
    store = TraceStore(tmp_path / "traces")
    answer_with_privacy(
        "What was the balance?",
        _Retriever(),
        _Generator(),
        local_model="local",
        mode="local",
        category="single_doc",
        trace_store=store,
    )
    cloud = answer_with_privacy(
        "What was the balance?",
        _Retriever(),
        _Generator(),
        local_model="local",
        mode="cloud",
        cloud_consent=True,
        cloud_generator=_Generator(),
        cloud_model="hosted/test",
        category="adversarial",
        trace_store=store,
        input_per_million_usd=2.0,
        output_per_million_usd=4.0,
    )
    assert cloud.trace is not None and cloud.trace.cost_usd > 0
    assert cloud.answer.routing.actual_cost_usd == cloud.trace.cost_usd

    rollups = trace_rollups(store.load())
    assert set(rollups) == {"feature", "category", "tier", "variant", "health"}
    assert rollups["feature"]["query"]["queries"] == 2
    assert rollups["category"]["adversarial"]["cost_usd"] == cloud.trace.cost_usd
    assert rollups["tier"]["T1"]["cost_usd"] == 0.0
    assert rollups["tier"]["T2"]["cost_usd"] == cloud.trace.cost_usd
    assert rollups["variant"]["B_hybrid"]["queries"] == 2
    assert rollups["health"]["all"]["queries"] == 2


def test_langfuse_export_is_optional_when_dependency_is_absent(tmp_path):
    store = TraceStore(tmp_path / "traces")
    routed = answer_with_privacy(
        "balance?",
        _Retriever(),
        _Generator(),
        local_model="local",
        trace_store=store,
    )
    assert routed.trace is not None
    assert export_to_langfuse(routed.trace) is False


def test_abstention_trace_keeps_complete_stage_topology(tmp_path):
    abstain = json.dumps(
        {
            "answer_text": "I couldn't find that in your documents.",
            "abstained": True,
            "citations": [],
        }
    )
    routed = answer_with_privacy(
        "What is the credit score?",
        _Retriever(),
        _Generator([abstain]),
        local_model="local",
        trace_store=TraceStore(tmp_path / "traces"),
    )
    assert routed.answer.abstained
    assert {span.name for span in routed.trace.spans} >= {
        "route",
        "retrieve",
        "assemble",
        "guards_in",
        "generate_repair",
        "guards_out",
    }
