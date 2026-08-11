"""Small deterministic state transitions shared with the Streamlit UI."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping


def sync_sample_question(
    state: MutableMapping[str, object],
    *,
    corpus: str,
    sample: str,
    questions: Mapping[str, str],
) -> None:
    """Reset the question only when its corpus/example source changes."""

    source = (corpus, sample)
    if state.get("question_source") != source:
        state["question_input"] = questions[sample]
        state["question_source"] = source


__all__ = ["sync_sample_question"]
