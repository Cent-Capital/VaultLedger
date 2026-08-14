"""ADR-0020's fixed replay rule and rejection rollback tests."""

from __future__ import annotations

from vaultledger.generate.reliable import verify_citations
from vaultledger.generate.schema import AnswerDraft, DraftCitation
from vaultledger.guardrails.support import (
    extract_named_entities,
    unsupported_named_entities,
)
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk, Citation


def _hit(text: str) -> ScoredChunk:
    chunk = Chunk(
        chunk_id="support#c0",
        doc_id="support",
        text=text,
        page=1,
        char_start=0,
        char_end=len(text),
    )
    return ScoredChunk(chunk=chunk, score=1.0, rank=1, source="test")


def _draft(answer_text: str, snippet: str) -> AnswerDraft:
    return AnswerDraft(
        answer_text=answer_text,
        citations=[DraftCitation(chunk_id="support#c0", snippet=snippet)],
    )


def _citation(snippet: str) -> Citation:
    return Citation(
        chunk_id="support#c0",
        doc_id="support",
        page=1,
        snippet=snippet,
    )


def test_fixed_rule_flags_unsupported_entity_by_name():
    snippet = "Halcyon Retail Group appears on every monthly statement."
    unsupported = unsupported_named_entities(
        "Halcyon Retail Group and CVS Pharmacy recur monthly.",
        "Which merchants recur monthly?",
        [_citation(snippet)],
    )

    assert unsupported == ["CVS Pharmacy"]


def test_entities_in_surviving_snippets_are_supported():
    snippet = "Halcyon Retail Group and CVS Pharmacy recur monthly."
    unsupported = unsupported_named_entities(
        "Halcyon Retail Group and CVS Pharmacy recur monthly.",
        "Which merchants recur monthly?",
        [_citation(snippet.lower())],
    )

    assert unsupported == []


def test_entity_present_only_in_question_is_supported():
    snippet = "The closing balance was $4,207.55."
    unsupported = unsupported_named_entities(
        "Marcus Chen had a closing balance of $4,207.55.",
        "What was Marcus Chen's closing balance?",
        [_citation(snippet)],
    )

    assert unsupported == []


def test_computed_total_absent_from_snippets_is_out_of_scope():
    snippet = "The two payments were $12,000.00 and $8,500.00."
    unsupported = unsupported_named_entities(
        "The computed total was $20,500.00.",
        "What was the computed total?",
        [_citation(snippet)],
    )

    assert unsupported == []


def test_stoplist_and_sentence_initial_common_word_are_not_entities():
    entities = extract_named_entities(
        "The balance was unchanged. March and Monday were listed. Netflix recurred."
    )

    assert entities == ["Netflix"]


def test_failed_rule_is_not_shipped_in_product_verifier():
    snippet = "Halcyon Retail Group appears on every monthly statement."
    result = verify_citations(
        _draft("Halcyon Retail Group and CVS Pharmacy recur monthly.", snippet),
        [_hit(snippet)],
    )

    assert not result.downgrade_to_abstain
    assert len(result.citations) == 1
