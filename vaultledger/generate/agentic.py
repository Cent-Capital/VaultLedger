"""Variant-D answer orchestration over the bounded L4 agent loop."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from vaultledger.generate.reliable import (
    MIN_SNIPPET_CHARS,
    VerifyResult,
    follows_injected_instruction,
    verify_citations,
)
from vaultledger.generate.schema import ABSTAIN_SENTENCE, AnswerDraft
from vaultledger.guardrails import GuardrailToggles
from vaultledger.guardrails.input import guard_query
from vaultledger.guardrails.output import (
    advice_linter,
    cited_doc_ids,
    cross_persona_check,
    load_invoice_totals,
    load_personas,
    numeric_verify,
)
from vaultledger.observability import TraceRecorder
from vaultledger.retrieve.agentic import AgenticRetriever, AgentPlanner, run_agent_loop
from vaultledger.schemas import Answer, Citation, GuardrailEvent, RoutingDecision


def _routing(model_id: str) -> RoutingDecision:
    return RoutingDecision(
        query_id=f"q_{uuid4().hex[:12]}",
        allowed_tiers=["T1"],
        chosen_tier="T1",
        chosen_model=model_id,
        reason="Phase 14 local agentic path: fixed model, bounded L4 loop",
        est_cost_usd=0.0,
        actual_cost_usd=0.0,
    )


def _confidence(citations: list[Citation], hits: list[object]) -> float:
    scores = {hit.chunk.chunk_id: hit.score for hit in hits}  # type: ignore[attr-defined]
    return max((scores.get(citation.chunk_id, 0.0) for citation in citations), default=0.0)


def answer_question_agentic(
    question: str,
    retriever: AgenticRetriever,
    planner: AgentPlanner,
    *,
    model_id: str,
    max_steps: int,
    token_budget: int,
    output_tokens_max: int,
    seconds_budget: float | None = None,
    k: int = 6,
    min_snippet_chars: int = MIN_SNIPPET_CHARS,
    routing: RoutingDecision | None = None,
    privacy_mode: str = "local",
    data_left_machine: bool = False,
    trace_recorder: TraceRecorder | None = None,
    guardrail_toggles: GuardrailToggles | None = None,
    records_db: str | Path | None = None,
    numeric_epsilon: float = 0.01,
) -> Answer:
    """Answer through L4, returning a valid Answer on every bounded exit path."""
    routing = routing or _routing(model_id)
    events: list[GuardrailEvent] = []

    def abstain(
        *,
        steps: list | None = None,
        text: str = ABSTAIN_SENTENCE,
    ) -> Answer:
        return Answer(
            answer_text=text,
            citations=[],
            abstained=True,
            confidence=0.0,
            model_used=model_id,
            tier=routing.chosen_tier,
            variant="D_agentic",
            privacy_mode=privacy_mode,  # type: ignore[arg-type]
            data_left_machine=data_left_machine,
            routing=routing,
            guardrail_events=events,
            agent_steps=steps or [],
        )

    if guardrail_toggles is not None:
        query_result = guard_query(
            question,
            injection_enabled=guardrail_toggles.query_injection_guard,
            advice_enabled=guardrail_toggles.advice_steer,
        )
        events.extend(query_result.events)
        if query_result.blocked or query_result.fixed_response:
            answer = abstain(text=query_result.fixed_response or ABSTAIN_SENTENCE)
            if trace_recorder:
                with trace_recorder.span("guards_in", short_circuit=True):
                    pass
                trace_recorder.finish(answer, avg_retrieval_score=0.0)
            return answer

    if trace_recorder:
        with trace_recorder.span(
            "agent_loop", max_steps=max_steps, token_budget=token_budget
        ):
            loop = run_agent_loop(
                question,
                retriever,
                planner,
                max_steps=max_steps,
                token_budget=token_budget,
                output_tokens_max=output_tokens_max,
                retrieve_k=k,
                seconds_budget=seconds_budget,
            )
        trace_recorder.add_estimated_tokens(
            input_chars=sum(step.tokens_used for step in loop.steps) * 4,
            output_chars=0,
        )
    else:
        loop = run_agent_loop(
            question,
            retriever,
            planner,
            max_steps=max_steps,
            token_budget=token_budget,
            output_tokens_max=output_tokens_max,
            retrieve_k=k,
            seconds_budget=seconds_budget,
        )

    if loop.injection_removed:
        events.append(
            GuardrailEvent(
                stage="input",
                guard="prompt_injection",
                action="block",
                details="instruction-like document line removed from agent observation",
            )
        )

    def finish_trace(answer: Answer) -> Answer:
        if trace_recorder:
            avg = sum(hit.score for hit in loop.hits) / len(loop.hits) if loop.hits else 0.0
            trace_recorder.finish(answer, avg_retrieval_score=avg)
        return answer

    if loop.action is None or loop.exhausted:
        if loop.token_exhausted:
            reason = "token budget"
        elif loop.time_exhausted:
            reason = "wall-clock budget"
        else:
            reason = "step budget"
        # An abstention caused by an unreachable generator must not read as the
        # model failing to answer — that is how Phase 14's outage was first
        # mistaken for model incompetence (ADR-0007).
        transport = (
            f"; {loop.transport_errors} transport failure(s), not model output"
            if loop.transport_errors
            else ""
        )
        events.append(
            GuardrailEvent(
                stage="output",
                guard="agent_budget",
                action="downgrade_to_abstain",
                details=(
                    f"agent exhausted its {reason}{transport}; "
                    "returned partial trace [TOOL_ERR]"
                ),
            )
        )
        return finish_trace(abstain(steps=loop.steps))

    action = loop.action
    if action.abstained:
        return finish_trace(abstain(steps=loop.steps))

    draft = AnswerDraft(
        answer_text=action.answer_text,
        abstained=False,
        citations=[citation.model_dump() for citation in action.citations],
    )
    citation_enabled = guardrail_toggles is None or guardrail_toggles.citation_verify
    verify = (
        verify_citations(
            draft, loop.hits, question, min_snippet_chars=min_snippet_chars
        )
        if citation_enabled
        else VerifyResult(
            citations=[
                Citation(
                    chunk_id=hit.chunk.chunk_id,
                    doc_id=hit.chunk.doc_id,
                    page=hit.chunk.page,
                    snippet=citation.snippet,
                    corpus=hit.chunk.corpus,
                    ocr_derived=hit.chunk.ocr_derived,
                )
                for citation in action.citations
                for hit in loop.hits
                if hit.chunk.chunk_id == citation.chunk_id
            ]
        )
    )
    events.extend(verify.events)
    if verify.downgrade_to_abstain:
        loop.steps[-1].failure = "finish rejected: citation verification failed"
        return finish_trace(abstain(steps=loop.steps))
    if follows_injected_instruction(action.answer_text):
        events.append(
            GuardrailEvent(
                stage="output",
                guard="prompt_injection",
                action="downgrade_to_abstain",
                details="agent finish appeared to follow an embedded instruction",
            )
        )
        loop.steps[-1].failure = "finish rejected: injection tripwire"
        return finish_trace(abstain(steps=loop.steps))

    answer = Answer(
        answer_text=action.answer_text.strip(),
        citations=verify.citations,
        abstained=False,
        confidence=max(0.0, min(1.0, _confidence(verify.citations, loop.hits))),
        model_used=model_id,
        tier=routing.chosen_tier,
        variant="D_agentic",
        privacy_mode=privacy_mode,  # type: ignore[arg-type]
        data_left_machine=data_left_machine,
        routing=routing,
        guardrail_events=events,
        agent_steps=loop.steps,
    )

    guard_db = Path(records_db) if records_db is not None else retriever.records_db
    if guardrail_toggles is not None and guardrail_toggles.numeric_verify:
        numeric = numeric_verify(
            question,
            answer.answer_text,
            load_invoice_totals(guard_db, cited_doc_ids(answer.citations)),
            epsilon=numeric_epsilon,
        )
        events.extend(numeric.events)
        if numeric.downgrade_to_abstain:
            loop.steps[-1].failure = "finish rejected: numeric verifier"
            return finish_trace(abstain(steps=loop.steps))
    if guardrail_toggles is not None and guardrail_toggles.cross_persona_check:
        isolation = cross_persona_check(question, answer.answer_text, load_personas(guard_db))
        events.extend(isolation.events)
        if isolation.downgrade_to_abstain:
            loop.steps[-1].failure = "finish rejected: cross-persona guard"
            return finish_trace(abstain(steps=loop.steps))
    if guardrail_toggles is not None and guardrail_toggles.advice_linter:
        advice = advice_linter(answer.answer_text)
        events.extend(advice.events)
        if advice.downgrade_to_abstain:
            loop.steps[-1].failure = "finish rejected: advice linter"
            return finish_trace(
                abstain(
                    steps=loop.steps,
                    text=advice.replacement_text or ABSTAIN_SENTENCE,
                )
            )
    answer.guardrail_events = list(events)
    return finish_trace(answer)


__all__ = ["answer_question_agentic"]
