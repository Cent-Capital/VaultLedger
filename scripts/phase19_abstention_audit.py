"""Build Phase 19's causal baseline for answerable abstentions.

The Phase 18 matrix receipt contains final answers and guard events, but it does
not say *which layer* caused an abstention or whether widening retrieval would
have supplied new evidence.  This script joins that receipt to the golden set,
classifies every answerable abstention, and replays retrieval without making a
generation call.  The output is a diagnostic receipt, not an accuracy result.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vaultledger.config import REPO_ROOT, load_config
from vaultledger.evals.golden import DEFAULT_GOLDEN_PATH, golden_hash, load_golden_set
from vaultledger.ingest.pipeline import assert_evaluation_corpus
from vaultledger.provenance import config_hash, git_output, sha256_file
from vaultledger.schemas import QAExample

DEFAULT_ANSWERS = (
    REPO_ROOT
    / "reports"
    / "phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f_answers.json"
)
DEFAULT_OUTPUT = REPO_ROOT / "receipts" / "phase19_abstention_baseline.json"


def abstention_source(row: dict[str, Any]) -> str | None:
    """Return the layer that finalized an abstention in a matrix answer row."""
    answer = row.get("answer")
    if not isinstance(answer, dict) or not answer.get("abstained"):
        return None
    events = answer.get("guardrail_events", [])
    if not isinstance(events, list):
        raise ValueError(f"{row.get('example_id', '<unknown>')}: guardrail_events is not a list")
    if any(
        event.get("guard") == "query_injection_guard" and event.get("action") == "block"
        for event in events
    ):
        return "query_block"
    if any(event.get("action") == "downgrade_to_abstain" for event in events):
        return "guard_downgrade"
    return "model_declared"


def _guard_downgrade_names(row: dict[str, Any]) -> list[str]:
    events = row["answer"].get("guardrail_events", [])
    return sorted(
        {
            str(event.get("guard", "unknown"))
            for event in events
            if event.get("action") == "downgrade_to_abstain"
        }
    )


def audit_rows(
    rows: list[dict[str, Any]], examples: list[QAExample]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Audit a complete answers receipt against its authoritative golden set."""
    expected = {example.id: example for example in examples}
    row_ids = [str(row.get("example_id", "")) for row in rows]
    duplicates = sorted(example_id for example_id, n in Counter(row_ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"duplicate answer rows: {', '.join(duplicates)}")
    missing = sorted(set(expected) - set(row_ids))
    extra = sorted(set(row_ids) - set(expected))
    if missing or extra:
        raise ValueError(f"answer receipt population mismatch: missing={missing}, extra={extra}")

    answerable = [example for example in examples if example.category != "unanswerable"]
    unanswerable = [example for example in examples if example.category == "unanswerable"]
    false_rows: list[dict[str, Any]] = []
    cause_counts: Counter[str] = Counter()
    downgrade_counts: Counter[str] = Counter()
    rightly_abstained = 0
    answered_unanswerable = 0
    judge_false_abstain = 0

    for row in rows:
        example_id = str(row["example_id"])
        example = expected[example_id]
        if row.get("category") != example.category:
            raise ValueError(
                f"{example_id}: row category {row.get('category')!r} does not match "
                f"golden category {example.category!r}"
            )
        answer = row.get("answer")
        if not isinstance(answer, dict) or not isinstance(answer.get("abstained"), bool):
            raise ValueError(f"{example_id}: missing typed answer.abstained")
        abstained = bool(answer["abstained"])
        if example.category == "unanswerable":
            rightly_abstained += int(abstained)
            answered_unanswerable += int(not abstained)
        elif abstained:
            source = abstention_source(row)
            if source is None:  # defensive: the branch above establishes abstained=True
                raise AssertionError("abstention source missing")
            cause_counts[source] += 1
            for guard in _guard_downgrade_names(row):
                downgrade_counts[guard] += 1
            false_rows.append(
                {
                    "example_id": example_id,
                    "category": example.category,
                    "source": source,
                    "downgrade_guards": _guard_downgrade_names(row),
                    "judge_failure_code": row.get("judge", {}).get("failure_code"),
                }
            )
        if row.get("judge", {}).get("failure_code") == "FALSE_ABSTAIN":
            judge_false_abstain += 1

    summary = {
        "rows": len(rows),
        "answerable_rows": len(answerable),
        "unanswerable_rows": len(unanswerable),
        "answerable_abstentions": len(false_rows),
        "rightly_abstained_unanswerable": rightly_abstained,
        "answered_unanswerable": answered_unanswerable,
        "judge_false_abstain": judge_false_abstain,
        "answerable_abstention_sources": dict(sorted(cause_counts.items())),
        "guard_downgrade_breakdown": dict(sorted(downgrade_counts.items())),
    }
    return summary, false_rows


def _retrieval_audit(
    false_rows: list[dict[str, Any]], examples: list[QAExample]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay retrieval for false-abstention rows; never call a generator."""
    from vaultledger.index.embed import OllamaEmbedder
    from vaultledger.retrieve import CrossEncoderReranker, HybridRetriever

    cfg = load_config()
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    assert_evaluation_corpus(index_dir)
    embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
    reranker = CrossEncoderReranker(cfg.reranker.model, cfg.reranker.batch_size)
    retriever = HybridRetriever(
        index_dir,
        embedder,
        candidate_k=cfg.retrieval.candidate_k,
        rank_constant=cfg.retrieval.rrf_constant,
        reranker=reranker,
    )
    by_id = {example.id: example for example in examples}
    replayed: list[dict[str, Any]] = []
    for audited in false_rows:
        example = by_id[audited["example_id"]]
        hits = retriever.retrieve(example.question, k=cfg.retrieval.answer_top_n * 2)
        expected_docs = set(example.expected_doc_ids)
        expected_ranks = [
            rank
            for rank, hit in enumerate(hits, 1)
            if hit.chunk.doc_id in expected_docs
        ]
        replayed.append(
            {
                **audited,
                "top_rerank_score": round(hits[0].score, 6) if hits else None,
                "below_rerank_tau": not hits or hits[0].score < cfg.thresholds.rerank_tau,
                "expected_doc_ranks": expected_ranks,
                "expected_doc_in_top_n": any(
                    rank <= cfg.retrieval.answer_top_n for rank in expected_ranks
                ),
                "expected_doc_in_doubled_top_n": bool(expected_ranks),
            }
        )

    summary = {
        "rows_replayed": len(replayed),
        "rerank_tau": cfg.thresholds.rerank_tau,
        "answer_top_n": cfg.retrieval.answer_top_n,
        "doubled_top_n": cfg.retrieval.answer_top_n * 2,
        "below_rerank_tau": sum(row["below_rerank_tau"] for row in replayed),
        "expected_doc_in_top_n": sum(row["expected_doc_in_top_n"] for row in replayed),
        "expected_doc_in_doubled_top_n": sum(
            row["expected_doc_in_doubled_top_n"] for row in replayed
        ),
    }
    return summary, replayed


def run(answers_path: Path, golden_path: Path, output: Path) -> dict[str, Any]:
    rows = json.loads(answers_path.read_text())
    if not isinstance(rows, list):
        raise ValueError("answers receipt must contain a top-level list")
    golden = load_golden_set(golden_path)
    baseline, false_rows = audit_rows(rows, golden.examples)
    retrieval, replayed = _retrieval_audit(false_rows, golden.examples)

    manifest_name = answers_path.name.removesuffix("_answers.json") + ".json"
    manifest_path = answers_path.with_name(manifest_name)
    if not manifest_path.exists():
        raise FileNotFoundError(f"source manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    receipt = {
        "receipt": "phase19_abstention_baseline_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": git_output("rev-parse", "HEAD"),
        "config_hash": config_hash(),
        "golden_set_hash": golden_hash(golden_path),
        "source_manifest": manifest.get("run_id"),
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_answers_sha256": sha256_file(answers_path),
        "baseline": baseline,
        "retrieval_replay": retrieval,
        "rows": replayed,
        "interpretation_boundary": (
            "This is a causal audit of an existing Phase 18 receipt plus a retrieval "
            "replay. It makes no claim that a changed abstention policy improves quality."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.answers, args.golden, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
