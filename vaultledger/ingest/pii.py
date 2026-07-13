"""PII tagging at ingest (SPEC.md Section 9 step 3, guardrail 13.1).

Microsoft Presidio's analyzer runs over each document's full text; detected
entity types and spans are stored per doc (``DocMeta.pii_entity_types``) for
later use by the egress redactor (Phase 13) and cross-persona leakage checks.

Two pragmatic choices, both logged in PROGRESS.md:
- spaCy ``en_core_web_sm`` instead of Presidio's default ``en_core_web_lg``:
  ~40x smaller download, sufficient recall on this corpus, and the model name
  is pinned here so results are comparable across machines.
- A custom recognizer for masked account numbers ("****4021"): the documents
  deliberately print only masked numbers, which the stock US_BANK_NUMBER
  recognizer (8-17 digit patterns) can never match. Without it the corpus's
  most sensitive token type would go untagged.
"""

from __future__ import annotations

from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

_SPACY_MODEL = "en_core_web_sm"

_ENTITIES = ["PERSON", "LOCATION", "DATE_TIME", "US_BANK_NUMBER", "EMAIL_ADDRESS", "PHONE_NUMBER"]


@dataclass
class PiiSpan:
    entity_type: str
    start: int
    end: int
    score: float


class PiiTagger:
    """Thin, lazily-constructed wrapper around Presidio's AnalyzerEngine."""

    def __init__(self) -> None:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": _SPACY_MODEL}],
            }
        )
        self._analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
        self._analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="US_BANK_NUMBER",
                name="masked_account_recognizer",
                patterns=[Pattern(name="masked_account", regex=r"\*{4}\d{4}", score=0.9)],
            )
        )

    def analyze(self, text: str) -> list[PiiSpan]:
        results = self._analyzer.analyze(text=text, language="en", entities=_ENTITIES)
        return [
            PiiSpan(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
            for r in results
        ]

    def entity_types(self, text: str) -> list[str]:
        """Sorted, de-duplicated entity types present in ``text``."""
        return sorted({span.entity_type for span in self.analyze(text)})


__all__ = ["PiiTagger", "PiiSpan"]
