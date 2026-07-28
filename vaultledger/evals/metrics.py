"""Retrieval metrics for the Phase 3 baseline (SPEC.md 12.2)."""

from __future__ import annotations

from collections.abc import Mapping

from vaultledger.schemas import QAExample


def abstention_confusion(
    examples: list[QAExample],
    outcomes: Mapping[str, tuple[bool, bool]],
) -> tuple[dict[str, float], list[dict]]:
    """Score answered-right/wrong and rightly/wrongly-abstained outcomes.

    ``outcomes[id]`` is ``(abstained, answer_correct)``. Correctness is ignored
    for abstentions. Missing outcomes are explicit failures, never silently
    removed from the denominator.
    """
    counts = {
        "answered_right": 0,
        "answered_wrong": 0,
        "rightly_abstained": 0,
        "wrongly_abstained": 0,
    }
    failures: list[dict] = []
    for ex in examples:
        outcome = outcomes.get(ex.id)
        if outcome is None:
            failures.append(
                {
                    "example_id": ex.id,
                    "taxonomy_code": "TOOL_ERR",
                    "note": "missing generation outcome",
                }
            )
            continue
        abstained, correct = outcome
        unanswerable = ex.category == "unanswerable"
        if abstained and unanswerable:
            counts["rightly_abstained"] += 1
        elif abstained:
            counts["wrongly_abstained"] += 1
            failures.append(
                {
                    "example_id": ex.id,
                    "taxonomy_code": "ABSTAIN_FP",
                    "note": "abstained on an answerable example",
                }
            )
        elif unanswerable:
            counts["answered_wrong"] += 1
            failures.append(
                {
                    "example_id": ex.id,
                    "taxonomy_code": "ABSTAIN_FN",
                    "note": "answered an unanswerable example",
                }
            )
        elif correct:
            counts["answered_right"] += 1
        else:
            counts["answered_wrong"] += 1

    evaluated = sum(counts.values())
    unanswerable_n = sum(ex.category == "unanswerable" for ex in examples)
    answerable_n = len(examples) - unanswerable_n
    metrics = {name: float(value) for name, value in counts.items()}
    metrics.update(
        {
            "abstention_unanswerable_recall": (
                counts["rightly_abstained"] / unanswerable_n if unanswerable_n else 0.0
            ),
            "abstention_answerable_specificity": (
                1.0 - counts["wrongly_abstained"] / answerable_n if answerable_n else 0.0
            ),
            "abstention_eval_coverage": evaluated / len(examples) if examples else 0.0,
        }
    )
    return metrics, failures


def retrieval_metrics(
    examples: list[QAExample],
    ranked_doc_ids: Mapping[str, list[str]],
    *,
    k: int,
) -> tuple[dict[str, float], list[dict]]:
    """Compute recall@k, precision@k, MRR, and hit-rate.

    Unanswerable examples have no expected documents, so they are excluded from
    retriever-only metrics and handled by generation/abstention evals later.
    """
    scored = [ex for ex in examples if ex.expected_doc_ids]
    if not scored:
        return {
            f"retrieval_recall@{k}": 0.0,
            f"retrieval_precision@{k}": 0.0,
            "retrieval_mrr": 0.0,
            "retrieval_hit_rate": 0.0,
            "retrieval_eval_coverage": 0.0,
        }, []

    recalls: list[float] = []
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    hits: list[float] = []
    failures: list[dict] = []

    for ex in scored:
        retrieved = ranked_doc_ids.get(ex.id, [])[:k]
        expected = set(ex.expected_doc_ids)
        retrieved_set = set(retrieved)
        found = expected & retrieved_set
        recalls.append(len(found) / len(expected))
        precisions.append(len(found) / max(min(k, len(retrieved)), 1))
        hits.append(1.0 if found else 0.0)

        rr = 0.0
        for rank, doc_id in enumerate(retrieved, 1):
            if doc_id in expected:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        if found != expected:
            missing = sorted(expected - found)
            failures.append(
                {
                    "example_id": ex.id,
                    "taxonomy_code": "RANK_MISS",
                    "note": f"missing expected docs in top-{k}: {', '.join(missing)}",
                }
            )

    n = len(scored)
    return {
        f"retrieval_recall@{k}": sum(recalls) / n,
        f"retrieval_precision@{k}": sum(precisions) / n,
        "retrieval_mrr": sum(reciprocal_ranks) / n,
        "retrieval_hit_rate": sum(hits) / n,
        "retrieval_eval_coverage": n / len(examples),
    }, failures


__all__ = ["retrieval_metrics", "abstention_confusion"]
