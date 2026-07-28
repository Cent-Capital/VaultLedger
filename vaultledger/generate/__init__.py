"""Grounded generation: prompts, local generation, and answer assembly.

- ``rag.answer_question`` — Phase 3 prose baseline (kept as a receipt).
- ``reliable.answer_question_reliable`` — Phase 5 product path: structured
  output + bounded repair (L1) + citation verification + safe fallback.
"""

from .ollama import GenerationError, OllamaGenerator, ollama_model_name
from .rag import answer_question, build_prompt
from .reliable import answer_question_reliable, repair_loop, verify_citations
from .schema import AnswerDraft, DraftParseError, parse_draft

__all__ = [
    "GenerationError",
    "OllamaGenerator",
    "ollama_model_name",
    "answer_question",
    "build_prompt",
    "answer_question_reliable",
    "repair_loop",
    "verify_citations",
    "AnswerDraft",
    "DraftParseError",
    "parse_draft",
]
