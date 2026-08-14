"""ADR-0020 support-aware citation-verification acceptance tests."""

from __future__ import annotations

from vaultledger.generate.reliable import extract_named_entities, verify_citations
from vaultledger.generate.schema import AnswerDraft, DraftCitation
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk


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


def test_unsupported_entity_downgrades_and_names_entity():
    snippet = "Halcyon Retail Group appears on every monthly statement."
    result = verify_citations(
        _draft("Halcyon Retail Group and CVS Pharmacy recur monthly.", snippet),
        [_hit(snippet)],
        "Which merchants recur monthly?",
    )

    assert result.downgrade_to_abstain and result.citations == []
    assert any(
        event.action == "downgrade_to_abstain"
        and event.guard == "citation_verify"
        and "CVS Pharmacy" in event.details
        and "CITE_FAIL" in event.details
        for event in result.events
    )


def test_entities_in_surviving_snippets_do_not_downgrade():
    snippet = "Halcyon Retail Group and CVS Pharmacy recur monthly."
    result = verify_citations(
        _draft("Halcyon Retail Group and CVS Pharmacy recur monthly.", snippet),
        [_hit(snippet.lower())],
        "Which merchants recur monthly?",
    )

    assert not result.downgrade_to_abstain
    assert len(result.citations) == 1


def test_entity_supported_only_by_question_does_not_downgrade():
    snippet = "The closing balance was $4,207.55."
    result = verify_citations(
        _draft("Marcus Chen had a closing balance of $4,207.55.", snippet),
        [_hit(snippet)],
        "What was Marcus Chen's closing balance?",
    )

    assert not result.downgrade_to_abstain


def test_computed_total_absent_from_snippets_does_not_downgrade():
    snippet = "The two payments were $12,000.00 and $8,500.00."
    result = verify_citations(
        _draft("The computed total was $20,500.00.", snippet),
        [_hit(snippet)],
        "What was the computed total?",
    )

    assert not result.downgrade_to_abstain


def test_stoplist_and_sentence_initial_common_word_are_not_entities():
    entities = extract_named_entities(
        "The balance was unchanged. March and Monday were listed. Netflix recurred."
    )

    assert entities == ["Netflix"]
