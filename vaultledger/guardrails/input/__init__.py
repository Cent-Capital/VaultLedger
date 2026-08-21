"""Pure input and ingest guards (SPEC 13.1)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vaultledger.schemas import GuardrailEvent, GuardrailStage

EDUCATION_NOT_ADVICE_RESPONSE = (
    "I can explain information in your documents, but I can't recommend financial, "
    "tax, or investment actions."
)

_INJECTION = re.compile(
    r"(?i)\b(?:system\s*:|ignore\s+(?:all\s+)?(?:prior|previous|your)\s+"
    r"(?:instructions?|rules)|list\s+(?:every|all)\s+account\s+numbers?|dump\s+all)\b"
)
_DIRECT_INJECTION = re.compile(
    r"(?is)^\s*(?:system\s*:|ignore\s+(?:all\s+)?(?:prior|previous|your)\s+"
    r"(?:instructions?|rules)|(?:reveal|dump|list)\s+(?:every|all))"
)
_ADVICE = re.compile(
    r"(?i)\b(?:should\s+i|what\s+should\s+i|do\s+you\s+recommend|recommend\s+(?:a|an|that|"
    r"buy|sell|invest)|is\s+.+\s+a\s+good\s+investment|which\s+(?:stock|fund|investment))\b"
)


class SpanLike(Protocol):
    entity_type: str


@dataclass(frozen=True)
class QueryGuardResult:
    events: tuple[GuardrailEvent, ...]
    blocked: bool = False
    fixed_response: str | None = None


def validate_file(filename: str, content: bytes, *, max_bytes: int) -> GuardrailEvent:
    """Validate extension, size, and PDF magic without parsing the document."""
    reasons = []
    if Path(filename).suffix.casefold() != ".pdf":
        reasons.append("extension is not .pdf")
    if len(content) > max_bytes:
        reasons.append(f"size {len(content)} exceeds cap {max_bytes}")
    if not content.startswith(b"%PDF-"):
        reasons.append("missing PDF magic bytes")
    return GuardrailEvent(
        stage="ingest",
        guard="file_validation",
        action="block" if reasons else "pass",
        details="; ".join(reasons) if reasons else f"accepted {filename} ({len(content)} bytes)",
    )


def pii_tagging_event(spans: Iterable[SpanLike]) -> GuardrailEvent:
    types = sorted({span.entity_type for span in spans})
    return GuardrailEvent(
        stage="ingest",
        guard="pii_tagging",
        action="pass",
        details=f"tagged entity types: {', '.join(types) if types else 'none'}",
    )


def injection_scan(text: str, *, stage: GuardrailStage = "ingest") -> GuardrailEvent:
    found = bool(_INJECTION.search(text))
    return GuardrailEvent(
        stage=stage,
        guard="injection_scan",
        action="flag" if found else "pass",
        details="instruction-like text detected" if found else "no instruction-like text detected",
    )


def guard_query(
    question: str,
    *,
    injection_enabled: bool = True,
    advice_enabled: bool = True,
) -> QueryGuardResult:
    events: list[GuardrailEvent] = []
    if injection_enabled:
        blocked = bool(_DIRECT_INJECTION.search(question))
        events.append(
            GuardrailEvent(
                stage="input",
                guard="query_injection_guard",
                action="block" if blocked else "pass",
                details=(
                    "direct instruction-override attempt blocked"
                    if blocked
                    else "no direct instruction-override attempt"
                ),
            )
        )
        if blocked:
            return QueryGuardResult(tuple(events), blocked=True)
    if advice_enabled:
        steered = bool(_ADVICE.search(question))
        events.append(
            GuardrailEvent(
                stage="input",
                guard="advice_steer",
                action="flag" if steered else "pass",
                details=(
                    "advice-seeking query routed to fixed education-not-advice response"
                    if steered
                    else "no advice-seeking intent detected"
                ),
            )
        )
        if steered:
            return QueryGuardResult(
                tuple(events), fixed_response=EDUCATION_NOT_ADVICE_RESPONSE
            )
    return QueryGuardResult(tuple(events))


__all__ = [
    "EDUCATION_NOT_ADVICE_RESPONSE",
    "QueryGuardResult",
    "guard_query",
    "injection_scan",
    "pii_tagging_event",
    "validate_file",
]
