"""Phase 12 deterministic local-size policy router and L3 escalation loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from vaultledger.generate.reliable import StructuredGenerator, answer_question_reliable
from vaultledger.retrieve import Retriever
from vaultledger.schemas import Answer, GuardrailEvent, RoutingDecision

LocalTier = Literal["T0", "T1"]
_TIER_ORDER: tuple[LocalTier, ...] = ("T0", "T1")


class BudgetExhausted(RuntimeError):
    """No configured local tier fits the remaining routing budget."""


@dataclass(frozen=True)
class PolicyAttempt:
    tier: LocalTier
    model: str
    answer: Answer
    escalation_trigger: str | None = None


@dataclass(frozen=True)
class PolicyAnswer:
    answer: Answer
    attempts: tuple[PolicyAttempt, ...]
    notice: str | None = None


class PolicyRouter:
    """Explainable T0/T1 policy with a pure, testable budget guard."""

    def __init__(
        self,
        *,
        models: Mapping[LocalTier, str],
        t0_categories: set[str] | frozenset[str],
        rerank_tau: float,
        projected_cost_usd: Mapping[LocalTier, float],
    ) -> None:
        self.models = dict(models)
        self.t0_categories = frozenset(t0_categories)
        self.rerank_tau = rerank_tau
        self.projected_cost_usd = dict(projected_cost_usd)
        missing_models = set(_TIER_ORDER) - self.models.keys()
        missing_costs = set(_TIER_ORDER) - self.projected_cost_usd.keys()
        if missing_models or missing_costs:
            raise ValueError(
                f"router requires T0/T1 models and costs; missing "
                f"models={sorted(missing_models)}, costs={sorted(missing_costs)}"
            )
        if any(cost < 0 for cost in self.projected_cost_usd.values()):
            raise ValueError("projected tier costs cannot be negative")

    def affordable_tiers(self, remaining_budget_usd: float) -> list[LocalTier]:
        return [
            tier
            for tier in _TIER_ORDER
            if self.projected_cost_usd[tier] <= max(0.0, remaining_budget_usd)
        ]

    def decide(
        self,
        *,
        category: str,
        retrieval_confidence: float | None = None,
        remaining_budget_usd: float,
        query_id: str | None = None,
    ) -> RoutingDecision:
        affordable = self.affordable_tiers(remaining_budget_usd)
        if not affordable:
            raise BudgetExhausted(
                f"no local tier fits remaining budget ${remaining_budget_usd:.6f}"
            )

        desired: LocalTier = "T0" if category in self.t0_categories else "T1"
        reasons = [f"category={category} -> {desired}"]
        if retrieval_confidence is not None and retrieval_confidence < self.rerank_tau:
            desired = "T1"
            reasons.append(
                f"retrieval_confidence={retrieval_confidence:.3f} < "
                f"tau={self.rerank_tau:.3f} -> T1"
            )
        if desired not in affordable:
            desired = affordable[-1]
            reasons.append(
                f"budget=${remaining_budget_usd:.6f} capped route to {desired}"
            )
        return RoutingDecision(
            query_id=query_id or f"q_{uuid4().hex[:12]}",
            allowed_tiers=affordable,
            chosen_tier=desired,
            chosen_model=self.models[desired],
            reason="; ".join(reasons),
            escalations=0,
            est_cost_usd=self.projected_cost_usd[desired],
            actual_cost_usd=0.0,
        )

    def next_tier(
        self, current: LocalTier, *, remaining_budget_usd: float
    ) -> LocalTier | None:
        affordable = self.affordable_tiers(remaining_budget_usd)
        current_index = _TIER_ORDER.index(current)
        return next(
            (tier for tier in affordable if _TIER_ORDER.index(tier) > current_index),
            None,
        )


def escalation_trigger(answer: Answer, *, category: str, rerank_tau: float) -> str | None:
    """Return the first observable L3 trigger, or ``None`` when the answer is viable."""
    downgrade = next(
        (event for event in answer.guardrail_events if event.action == "downgrade_to_abstain"),
        None,
    )
    if downgrade is not None:
        return f"{downgrade.guard} downgraded output"
    if answer.abstained and category != "unanswerable":
        return "model abstained on an answerable category"
    if not answer.abstained and answer.confidence < rerank_tau:
        return f"answer confidence {answer.confidence:.3f} below tau {rerank_tau:.3f}"
    return None


def _answer_rank(answer: Answer) -> tuple[int, float]:
    downgraded = any(
        event.action == "downgrade_to_abstain" for event in answer.guardrail_events
    )
    return (int(not answer.abstained and not downgraded), answer.confidence)


def answer_with_policy(
    question: str,
    retriever: Retriever,
    generators: Mapping[LocalTier, StructuredGenerator],
    *,
    router: PolicyRouter,
    category: str,
    remaining_budget_usd: float,
    retrieval_confidence: float | None = None,
    escalation_max: int = 2,
    k: int = 20,
    max_retries: int = 2,
    min_snippet_chars: int = 16,
) -> PolicyAnswer:
    """Answer under policy v2 with an explicit bounded T0→T1 escalation loop."""
    decision = router.decide(
        category=category,
        retrieval_confidence=retrieval_confidence,
        remaining_budget_usd=remaining_budget_usd,
    )
    attempts: list[PolicyAttempt] = []
    spent = 0.0
    current: LocalTier = decision.chosen_tier  # type: ignore[assignment]

    for escalation_count in range(escalation_max + 1):
        if current not in generators:
            raise ValueError(f"no generator configured for routed tier {current}")
        attempt_decision = RoutingDecision(
            query_id=decision.query_id,
            allowed_tiers=decision.allowed_tiers,
            chosen_tier=current,
            chosen_model=router.models[current],
            reason=decision.reason,
            escalations=escalation_count,
            est_cost_usd=router.projected_cost_usd[current],
            actual_cost_usd=0.0,
        )
        answer = answer_question_reliable(
            question,
            retriever,
            generators[current],
            model_id=router.models[current],
            k=k,
            max_retries=max_retries,
            min_snippet_chars=min_snippet_chars,
            routing=attempt_decision,
        )
        spent += router.projected_cost_usd[current]
        trigger = escalation_trigger(answer, category=category, rerank_tau=router.rerank_tau)
        attempts.append(PolicyAttempt(current, router.models[current], answer, trigger))
        if trigger is None:
            break
        remaining = remaining_budget_usd - spent
        next_tier = router.next_tier(current, remaining_budget_usd=remaining)
        if next_tier is None or escalation_count == escalation_max:
            break
        decision.reason += f"; escalation {escalation_count + 1}: {trigger} -> {next_tier}"
        current = next_tier

    best = max(attempts, key=lambda attempt: _answer_rank(attempt.answer))
    final = best.answer
    escalations = max(0, len(attempts) - 1)
    final.routing = RoutingDecision(
        query_id=decision.query_id,
        allowed_tiers=decision.allowed_tiers,
        chosen_tier=best.tier,
        chosen_model=best.model,
        reason=(
            decision.reason
            + (
                f"; kept {best.tier} as safest best attempt after {escalations} escalation(s)"
                if escalations
                else ""
            )
        ),
        escalations=escalations,
        est_cost_usd=sum(
            router.projected_cost_usd[attempt.tier] for attempt in attempts
        ),
        actual_cost_usd=0.0,
    )
    if escalations:
        final.guardrail_events.append(
            GuardrailEvent(
                stage="output",
                guard="router_escalation",
                action="flag",
                details=decision.reason,
            )
        )
    notice = None
    if "capped route" in decision.reason:
        notice = "Routing tier capped by remaining budget"
    return PolicyAnswer(final, tuple(attempts), notice)


__all__ = [
    "BudgetExhausted",
    "LocalTier",
    "PolicyAnswer",
    "PolicyAttempt",
    "PolicyRouter",
    "answer_with_policy",
    "escalation_trigger",
]
