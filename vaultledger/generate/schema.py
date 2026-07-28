"""LLM-facing answer schema + tolerant JSON parsing (SPEC.md 9.11, FR7).

Phase 5 forces the generator to emit a small, validated JSON object rather than
free prose. This module owns:

- ``AnswerDraft`` — the *only* thing the model is asked to produce. The rich
  ``Answer`` contract (tier, routing, confidence, privacy) is filled by the
  orchestrator, never by the model, so a hallucinated ``model_used`` or
  ``data_left_machine`` is structurally impossible.
- ``ANSWER_JSON_SCHEMA`` — handed to Ollama's ``format`` field for constrained
  decoding.
- ``parse_draft`` — validates raw model output into an ``AnswerDraft`` and
  raises ``DraftParseError`` (with a repair-friendly message) on any failure.

Keeping the schema and parser model-free is deliberate: the Phase 5 repair loop
and citation verifier can then be tested against recorded/synthetic generations
with no live model, which is exactly what the CI eval gate needs (SPEC 15.5).
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

# The fixed abstention sentence, shared by the prompt and the fallback path so
# the string the model is told to emit is byte-identical to the one we detect.
ABSTAIN_SENTENCE = "I couldn't find that in your documents."


class DraftCitation(BaseModel):
    """One citation as claimed by the model, before verification."""

    chunk_id: str
    snippet: str = ""


class AnswerDraft(BaseModel):
    """The model's structured output. Verified downstream; trusted nowhere."""

    model_config = {"extra": "forbid"}

    answer_text: str
    abstained: bool = False
    citations: list[DraftCitation] = Field(default_factory=list)


# JSON Schema handed to Ollama's ``format`` for constrained decoding. Derived
# from the model so the two never drift.
ANSWER_JSON_SCHEMA = AnswerDraft.model_json_schema()


class DraftParseError(ValueError):
    """Raised when raw model output cannot be validated into an AnswerDraft.

    The message is written to be fed straight back into the repair prompt, so
    it names what was wrong in terms the model can act on.
    """


def _extract_json_object(raw: str) -> str:
    """Best-effort pull of a single JSON object out of noisy model output.

    Constrained decoding usually yields clean JSON, but a model may still wrap
    it in prose or ```json fences. We take the span from the first ``{`` to the
    last ``}``; anything more clever risks silently accepting the wrong object.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DraftParseError(
            "Output was not JSON. Return ONLY a JSON object with keys "
            '"answer_text", "abstained", "citations".'
        )
    return raw[start : end + 1]


def parse_draft(raw: str) -> AnswerDraft:
    """Validate raw model output into an ``AnswerDraft`` or raise.

    Raises ``DraftParseError`` with a repair-friendly message on empty output,
    non-JSON, malformed JSON, or schema-invalid JSON.
    """
    if not raw or not raw.strip():
        raise DraftParseError(
            "Output was empty. Return a JSON object with keys "
            '"answer_text", "abstained", "citations".'
        )
    candidate = _extract_json_object(raw)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DraftParseError(
            f"Output was not valid JSON ({exc.msg}). Return a single, complete "
            "JSON object and nothing else."
        ) from exc
    if not isinstance(data, dict):
        raise DraftParseError(
            "Output JSON must be an object, not a list or scalar."
        )
    try:
        return AnswerDraft.model_validate(data)
    except ValidationError as exc:
        # Compact the pydantic error into a single actionable line.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        )
        raise DraftParseError(
            f"JSON did not match the required schema ({problems}). Keys must be "
            'exactly "answer_text" (string), "abstained" (bool), "citations" '
            '(list of {"chunk_id", "snippet"}).'
        ) from exc


__all__ = [
    "ABSTAIN_SENTENCE",
    "DraftCitation",
    "AnswerDraft",
    "ANSWER_JSON_SCHEMA",
    "DraftParseError",
    "parse_draft",
]
