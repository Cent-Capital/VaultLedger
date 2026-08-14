"""Fixed ADR-0020 entity-support rule retained for deterministic replay.

The rule failed its preregistered false-positive gate and is not called by the
product verifier. Keeping the unchanged extractor here makes the negative result
reproducible without shipping the rejected behavior.
"""

from __future__ import annotations

import re

from vaultledger.schemas import Citation

# ADR-0020 fixed these lexical exclusions before the historical replay.
# Numeric tokens never enter the extractor, so amounts and dates remain owned by
# numeric_verify rather than citation entity coverage.
ENTITY_STOPLIST = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "i",
        "couldn't",
        "find",
        "that",
        "in",
        "your",
        "documents",
    }
)
_SENTENCE_INITIAL_COMMON_WORDS = frozenset(
    {
        "a",
        "according",
        "an",
        "and",
        "as",
        "at",
        "based",
        "because",
        "but",
        "by",
        "for",
        "from",
        "here",
        "however",
        "if",
        "in",
        "it",
        "its",
        "no",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "we",
        "when",
        "where",
        "which",
        "while",
        "with",
        "yes",
        "you",
    }
)
_CAPITALIZED_TOKEN = r"[A-Z][A-Za-z]*(?:['’][A-Za-z]+)?"
_CAPITALIZED_TOKEN_RE = re.compile(_CAPITALIZED_TOKEN)
_ENTITY_SPAN = re.compile(
    rf"(?<![A-Za-z0-9_]){_CAPITALIZED_TOKEN}(?:\s+{_CAPITALIZED_TOKEN})*"
)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def _is_sentence_initial(text: str, start: int) -> bool:
    """Return whether ``start`` follows a sentence or list-item boundary."""
    prefix = text[:start]
    line_prefix = prefix[prefix.rfind("\n") + 1 :]
    if not line_prefix.strip(" \t-*•"):
        return True
    stripped = prefix.rstrip().rstrip('"\'“”‘’([{')
    return not stripped or stripped[-1] in ".!?"


def extract_named_entities(text: str) -> list[str]:
    """Extract deterministic ADR-0020 named-entity claim units from ``text``."""
    entities: list[str] = []
    seen: set[str] = set()
    candidates: list[tuple[str, int]] = []
    for span in _ENTITY_SPAN.finditer(text):
        current: list[str] = []
        current_start = span.start()
        for token in _CAPITALIZED_TOKEN_RE.finditer(span.group(0)):
            token_text = token.group(0)
            token_key = _normalize(token_text)
            if token_key in ENTITY_STOPLIST:
                if current:
                    candidates.append((" ".join(current), current_start))
                    current = []
                continue
            if not current:
                current_start = span.start() + token.start()
            if token_text.lower().endswith(("'s", "’s")):
                token_text = token_text[:-2]
            current.append(token_text)
        if current:
            candidates.append((" ".join(current), current_start))

    for entity, start in candidates:
        key = _normalize(entity)
        if not key:
            continue
        if (
            " " not in entity
            and key in _SENTENCE_INITIAL_COMMON_WORDS
            and _is_sentence_initial(text, start)
        ):
            continue
        if key not in seen:
            entities.append(entity)
            seen.add(key)
    return entities


def unsupported_named_entities(
    answer_text: str,
    question: str,
    citations: list[Citation],
) -> list[str]:
    """Return answer entities absent from all surviving snippets and the question."""
    support = _normalize(" ".join([question, *(citation.snippet for citation in citations)]))
    return [
        entity
        for entity in extract_named_entities(answer_text)
        if _normalize(entity) not in support
    ]
