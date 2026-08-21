"""Durable local query traces, health metrics, and cost attribution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, Field

from vaultledger.schemas import Answer, PrivacyMode, Tier, Variant


class SpanRecord(BaseModel):
    name: str
    duration_ms: float
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class QueryTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    feature: str = "query"
    category: str = "interactive"
    model: str
    tier: Tier
    variant: Variant
    privacy_mode: PrivacyMode
    spans: list[SpanRecord] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    token_count_source: str = "estimated_chars_div_4"
    cost_usd: float = 0.0
    abstained: bool = False
    avg_retrieval_score: float = 0.0
    repair_triggered: bool = False
    guardrail_flagged: bool = False
    escalations: int = 0
    error: str | None = None


class TraceRecorder:
    """Build one trace. Timings use monotonic wall clock."""

    def __init__(
        self,
        *,
        model: str,
        tier: Tier,
        variant: Variant,
        privacy_mode: PrivacyMode,
        feature: str = "query",
        category: str = "interactive",
        input_per_million_usd: float = 0.0,
        output_per_million_usd: float = 0.0,
    ) -> None:
        self.trace = QueryTrace(
            model=model,
            tier=tier,
            variant=variant,
            privacy_mode=privacy_mode,
            feature=feature,
            category=category,
        )
        self._started = perf_counter()
        self._input_rate = input_per_million_usd
        self._output_rate = output_per_million_usd
        self._avg_retrieval_score: float | None = None

    @contextmanager
    def span(self, name: str, **metadata: str | int | float | bool) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.trace.spans.append(
                SpanRecord(
                    name=name,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    metadata=metadata,
                )
            )

    def add_estimated_tokens(self, *, input_chars: int = 0, output_chars: int = 0) -> None:
        self.trace.input_tokens += max(0, input_chars // 4)
        self.trace.output_tokens += max(0, output_chars // 4)

    def finish(
        self, answer: Answer, *, avg_retrieval_score: float | None = None
    ) -> QueryTrace:
        """Finalize the trace. Safe to call more than once.

        Both the reliable-answer path and the privacy router call this: the
        inner call supplies the retrieval score it alone can see, the outer
        call refreshes latency and cost once routing has finished. Values from
        an earlier call are retained rather than reset by a later one, so the
        outer call never blanks a health metric the inner call recorded.
        """
        self.trace.total_latency_ms = round((perf_counter() - self._started) * 1000, 3)
        self.trace.model = answer.model_used
        self.trace.tier = answer.tier
        self.trace.variant = answer.variant
        self.trace.privacy_mode = answer.privacy_mode
        self.trace.abstained = answer.abstained
        if avg_retrieval_score is not None:
            self._avg_retrieval_score = avg_retrieval_score
        if self._avg_retrieval_score is not None:
            self.trace.avg_retrieval_score = round(self._avg_retrieval_score, 6)
        self.trace.repair_triggered = any(
            event.guard == "structured_repair" for event in answer.guardrail_events
        )
        self.trace.guardrail_flagged = any(
            event.action != "pass" for event in answer.guardrail_events
        )
        self.trace.escalations = answer.routing.escalations
        self.trace.cost_usd = round(
            (
                self.trace.input_tokens * self._input_rate
                + self.trace.output_tokens * self._output_rate
            )
            / 1_000_000,
            8,
        )
        answer.routing.actual_cost_usd = self.trace.cost_usd
        return self.trace


class TraceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, trace: QueryTrace) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{trace.trace_id}.json"
        path.write_text(trace.model_dump_json(indent=2) + "\n")
        return path

    def load(self) -> list[QueryTrace]:
        if not self.directory.exists():
            return []
        return [
            QueryTrace.model_validate_json(path.read_text())
            for path in sorted(self.directory.glob("trace_*.json"))
        ]


def trace_rollups(traces: list[QueryTrace]) -> dict:
    """Aggregate cost/latency by feature, category, tier, and variant."""
    dimensions = ("feature", "category", "tier", "variant")
    rollups: dict[str, dict[str, dict[str, float]]] = {}
    for dimension in dimensions:
        groups: dict[str, list[QueryTrace]] = {}
        for trace in traces:
            groups.setdefault(str(getattr(trace, dimension)), []).append(trace)
        rollups[dimension] = {
            key: {
                "queries": float(len(rows)),
                "cost_usd": round(sum(row.cost_usd for row in rows), 8),
                "avg_latency_ms": round(
                    sum(row.total_latency_ms for row in rows) / len(rows), 3
                ),
            }
            for key, rows in groups.items()
        }
    n = len(traces)
    rollups["health"] = {
        "all": {
            "queries": float(n),
            "abstention_rate": sum(t.abstained for t in traces) / n if n else 0.0,
            "avg_retrieval_score": (
                sum(t.avg_retrieval_score for t in traces) / n if n else 0.0
            ),
            "repair_trigger_rate": (
                sum(t.repair_triggered for t in traces) / n if n else 0.0
            ),
            "guardrail_flag_rate": (
                sum(t.guardrail_flagged for t in traces) / n if n else 0.0
            ),
            "escalation_rate": (
                sum(t.escalations > 0 for t in traces) / n if n else 0.0
            ),
        }
    }
    return rollups


def export_to_langfuse(trace: QueryTrace) -> bool:
    """Best-effort optional export; local traces never depend on Langfuse.

    Returns True only when spans were handed to an authenticated client. An
    importable-but-unconfigured Langfuse disables itself silently, so the
    ``auth_check`` guard exists to stop this function reporting an export that
    never left the process. ``auth_check`` short-circuits without a network
    call when no credentials are present.
    """
    try:
        from langfuse import get_client  # type: ignore[import-not-found]
    except ImportError:
        return False
    client = get_client()
    if not client.auth_check():
        return False
    with client.start_as_current_observation(
        as_type="span",
        name="vaultledger.query",
        metadata=trace.model_dump(exclude={"spans"}),
    ):
        for recorded in trace.spans:
            with client.start_as_current_observation(
                as_type="span",
                name=recorded.name,
                metadata={
                    **recorded.metadata,
                    "measured_duration_ms": recorded.duration_ms,
                },
            ):
                pass
    client.flush()
    return True


__all__ = [
    "QueryTrace",
    "SpanRecord",
    "TraceRecorder",
    "TraceStore",
    "export_to_langfuse",
    "trace_rollups",
]
