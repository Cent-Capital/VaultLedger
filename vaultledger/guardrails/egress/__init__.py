"""Offline-testable Presidio-span egress redaction contract (SPEC 13.2)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from vaultledger.schemas import GuardrailEvent


class SpanLike(Protocol):
    entity_type: str
    start: int
    end: int


@dataclass(frozen=True)
class EgressResult:
    query: str
    context: str
    placeholders: dict[str, str]
    event: GuardrailEvent


_PREFIX = {
    "PERSON": "PERSON",
    "US_BANK_NUMBER": "ACCT",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "LOCATION": "LOCATION",
    "DATE_TIME": "DATE",
}


def redact_for_egress(
    query: str,
    context: str,
    analyze: Callable[[str], Iterable[SpanLike]],
) -> EgressResult:
    """Replace detected spans with stable placeholders across query and context."""
    raw_to_placeholder: dict[tuple[str, str], str] = {}
    placeholders: dict[str, str] = {}
    counters: dict[str, int] = {}

    def redact(text: str) -> str:
        spans = sorted(analyze(text), key=lambda span: (span.start, span.end))
        accepted: list[tuple[str, int, int]] = []
        cursor = -1
        for span in spans:
            end = span.end
            raw = text[span.start:end]
            # Presidio/spaCy sometimes includes the English possessive suffix in
            # a PERSON span. Preserve the suffix outside the placeholder so the
            # same name maps stably in possessive and non-possessive contexts.
            if span.entity_type == "PERSON" and raw.casefold().endswith(("'s", "’s")):
                end -= 2
            if span.start < cursor or span.start >= end:
                continue
            accepted.append((span.entity_type, span.start, end))
            cursor = end
        pieces: list[str] = []
        cursor = 0
        for entity_type, start, end in accepted:
            raw = text[start:end]
            prefix = _PREFIX.get(entity_type, entity_type)
            key = (entity_type, raw)
            placeholder = raw_to_placeholder.get(key)
            if placeholder is None:
                counters[prefix] = counters.get(prefix, 0) + 1
                placeholder = f"<{prefix}_{counters[prefix]}>"
                raw_to_placeholder[key] = placeholder
                placeholders[placeholder] = raw
            pieces.extend((text[cursor:start], placeholder))
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces)

    redacted_query = redact(query)
    redacted_context = redact(context)
    return EgressResult(
        query=redacted_query,
        context=redacted_context,
        placeholders=placeholders,
        event=GuardrailEvent(
            stage="egress",
            guard="pii_redaction",
            action="redact" if placeholders else "pass",
            details=f"replaced {len(placeholders)} unique PII values before egress",
        ),
    )


def rehydrate(text: str, placeholders: dict[str, str]) -> str:
    """Restore placeholders exactly; the map remains local to the process."""
    for placeholder in sorted(placeholders, key=len, reverse=True):
        text = text.replace(placeholder, placeholders[placeholder])
    return text


__all__ = ["EgressResult", "redact_for_egress", "rehydrate"]
