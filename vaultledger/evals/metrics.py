"""Retrieval metrics for the Phase 3 baseline (SPEC.md 12.2)."""

from __future__ import annotations

from collections.abc import Mapping

from vaultledger.schemas import QAExample


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


__all__ = ["retrieval_metrics"]
