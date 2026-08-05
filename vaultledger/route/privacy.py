"""Phase 6 privacy switch (routing v1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from vaultledger.generate.ollama import GenerationError
from vaultledger.generate.reliable import StructuredGenerator, answer_question_reliable
from vaultledger.guardrails import GuardrailToggles
from vaultledger.observability import (
    QueryTrace,
    TraceRecorder,
    TraceStore,
    export_to_langfuse,
)
from vaultledger.retrieve import Retriever
from vaultledger.schemas import Answer, GuardrailEvent, RoutingDecision

PrivacyMode = Literal["local", "cloud"]


class CloudConsentRequired(ValueError):
    """Cloud was requested without explicit consent for this session."""


@dataclass(frozen=True)
class RoutedAnswer:
    answer: Answer
    degraded: bool = False
    notice: str | None = None
    trace: QueryTrace | None = None


def _decision(
    model: str,
    mode: PrivacyMode,
    *,
    degraded: bool = False,
    cloud_attempted: bool = False,
) -> RoutingDecision:
    tier = "T1" if mode == "local" else "T2"
    reason = (
        (
            "Phase 6 degraded fallback: cloud request failed after egress attempt; "
            "answered locally"
            if cloud_attempted
            else "Phase 6 degraded fallback: cloud unavailable before egress; answered locally"
        )
        if degraded
        else f"Phase 6 privacy switch: user selected {mode}"
    )
    return RoutingDecision(
        query_id=f"q_{uuid4().hex[:12]}",
        allowed_tiers=(
            ["T0", "T1", "T2"]
            if mode == "cloud" or cloud_attempted
            else ["T0", "T1"]
        ),
        chosen_tier=tier,
        chosen_model=model,
        reason=reason,
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )


def answer_with_privacy(
    question: str,
    retriever: Retriever,
    local_generator: StructuredGenerator,
    *,
    local_model: str,
    mode: PrivacyMode = "local",
    cloud_consent: bool = False,
    cloud_generator: StructuredGenerator | None = None,
    cloud_model: str = "",
    k: int = 20,
    max_retries: int = 2,
    min_snippet_chars: int = 16,
    category: str = "interactive",
    trace_store: TraceStore | None = None,
    export_langfuse: bool = False,
    input_per_million_usd: float = 0.0,
    output_per_million_usd: float = 0.0,
    guardrail_toggles: GuardrailToggles | None = None,
    records_db: str | Path | None = None,
    numeric_epsilon: float = 0.01,
) -> RoutedAnswer:
    """Route one query without touching the cloud on the local branch."""
    recorder = TraceRecorder(
        model=local_model if mode == "local" else cloud_model or local_model,
        tier="T1" if mode == "local" else "T2",
        variant=retriever.variant,
        privacy_mode=mode,
        category=category,
        input_per_million_usd=input_per_million_usd if mode == "cloud" else 0.0,
        output_per_million_usd=output_per_million_usd if mode == "cloud" else 0.0,
    )
    with recorder.span("route", requested_mode=mode):
        pass

    def _result(
        answer: Answer,
        *,
        degraded: bool = False,
        notice: str | None = None,
    ) -> RoutedAnswer:
        trace = recorder.finish(answer)
        if trace_store:
            trace_store.save(trace)
        if export_langfuse:
            export_to_langfuse(trace)
        return RoutedAnswer(answer, degraded=degraded, notice=notice, trace=trace)

    common = {
        "k": k,
        "max_retries": max_retries,
        "min_snippet_chars": min_snippet_chars,
        "trace_recorder": recorder,
        "guardrail_toggles": guardrail_toggles,
        "records_db": records_db,
        "numeric_epsilon": numeric_epsilon,
    }
    if mode == "local":
        answer = answer_question_reliable(
            question, retriever, local_generator, model_id=local_model,
            routing=_decision(local_model, "local"), **common,
        )
        return _result(answer)

    if not cloud_consent:
        raise CloudConsentRequired("Confirm cloud use for this session before asking.")

    if cloud_generator is None or not cloud_model:
        recorder.trace.error = "cloud unavailable before egress"
        decision = _decision(local_model, "local", degraded=True)
        answer = answer_question_reliable(
            question, retriever, local_generator, model_id=local_model,
            routing=decision, **common,
        )
        answer.guardrail_events.insert(
            0,
            GuardrailEvent(
                stage="egress",
                guard="cloud_availability",
                action="flag",
                details="cloud unavailable before egress; local fallback used",
            ),
        )
        return _result(
            answer,
            degraded=True,
            notice="Cloud unavailable — answered locally",
        )

    try:
        answer = answer_question_reliable(
            question, retriever, cloud_generator, model_id=cloud_model,
            routing=_decision(cloud_model, "cloud"),
            privacy_mode="cloud", data_left_machine=True, **common,
        )
        return _result(answer)
    except GenerationError as exc:
        # The cloud generator was invoked with the assembled prompt. Be
        # conservative: a timeout, HTTP error, or malformed response can occur
        # after the provider received the data, so egress remains true even
        # though the local model ultimately produces the answer.
        recorder.trace.error = str(exc)
        decision = _decision(
            local_model, "local", degraded=True, cloud_attempted=True
        )
        answer = answer_question_reliable(
            question, retriever, local_generator, model_id=local_model,
            routing=decision,
            privacy_mode="cloud",
            data_left_machine=True,
            **common,
        )
        answer.guardrail_events.insert(
            0,
            GuardrailEvent(
                stage="egress",
                guard="cloud_availability",
                action="flag",
                details=f"cloud request failed after egress attempt; local fallback used: {exc}",
            ),
        )
        return _result(
            answer,
            degraded=True,
            notice="Cloud request failed — answered locally; data may have left your machine",
        )


__all__ = ["CloudConsentRequired", "PrivacyMode", "RoutedAnswer", "answer_with_privacy"]
