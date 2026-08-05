"""Named, ordered input/egress/output guardrail pipelines (Phase 13, SPEC 13)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailToggles:
    file_validation: bool = True
    pii_tagging: bool = True
    injection_scan: bool = True
    query_injection_guard: bool = True
    advice_steer: bool = True
    egress_redaction: bool = True
    citation_verify: bool = True
    numeric_verify: bool = True
    cross_persona_check: bool = True
    advice_linter: bool = True

    @classmethod
    def from_config(cls, value: object) -> GuardrailToggles:
        return cls(**{name: bool(getattr(value, name)) for name in cls.__dataclass_fields__})


__all__ = ["GuardrailToggles"]
