"""Replay ADR-0020 entity support over committed Phase 18 B_hybrid answers.

This script reads stored final answers, surviving citations, judge verdicts, and
strict scores. It never constructs a generator or makes a model call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vaultledger.config import CONFIG_PATH, REPO_ROOT
from vaultledger.evals.golden import DEFAULT_GOLDEN_PATH, golden_hash, load_golden_set
from vaultledger.generate.reliable import unsupported_named_entities
from vaultledger.schemas import Citation, QAExample

DEFAULT_OUTPUT = REPO_ROOT / "receipts" / "support_coverage_replay.json"
SOURCE_PATHSPEC = ":(glob)reports/phase18_*_b_hybrid_*_answers.json"
CANDIDATE_RUN_ID = "phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9"
CANDIDATE_DEFECT_ROW = "gs_005"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def committed_answer_paths() -> list[Path]:
    """Return every committed receipt in ADR-0020's Phase 18 B_hybrid population."""
    relative_paths = [line for line in _git("ls-files", "--", SOURCE_PATHSPEC).splitlines() if line]
    if not relative_paths:
        raise FileNotFoundError("no committed Phase 18 B_hybrid answer receipts found")
    paths = [REPO_ROOT / relative for relative in sorted(relative_paths)]
    if not any(path.name.removesuffix("_answers.json") == CANDIDATE_RUN_ID for path in paths):
        raise FileNotFoundError(
            f"required rejected-candidate receipt is missing: {CANDIDATE_RUN_ID}"
        )
    return paths


def replay_rows(
    rows: list[dict[str, Any]], examples: list[QAExample]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply only the new entity-support check to one complete stored population."""
    expected = {example.id: example for example in examples}
    row_ids = [str(row.get("example_id", "")) for row in rows]
    duplicates = sorted(example_id for example_id, n in Counter(row_ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"duplicate answer rows: {', '.join(duplicates)}")
    missing = sorted(set(expected) - set(row_ids))
    extra = sorted(set(row_ids) - set(expected))
    if missing or extra:
        raise ValueError(f"answer receipt population mismatch: missing={missing}, extra={extra}")

    downgraded: list[dict[str, Any]] = []
    answered_rows = 0
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
        if answer["abstained"]:
            continue
        answered_rows += 1
        answer_text = answer.get("answer_text")
        if not isinstance(answer_text, str) or not answer_text.strip():
            raise ValueError(f"{example_id}: surfaced answer has no answer_text")
        raw_citations = answer.get("citations")
        if not isinstance(raw_citations, list) or not raw_citations:
            raise ValueError(f"{example_id}: surfaced answer has no surviving citations")
        citations = [Citation.model_validate(citation) for citation in raw_citations]
        unsupported = unsupported_named_entities(answer_text, example.question, citations)
        if not unsupported:
            continue
        strict_passed = row.get("strict_match")
        judge = row.get("judge")
        if not isinstance(strict_passed, bool):
            raise ValueError(f"{example_id}: strict_match is not a boolean")
        if not isinstance(judge, dict) or not isinstance(judge.get("passed"), bool):
            raise ValueError(f"{example_id}: judge.passed is not a boolean")
        judge_passed = bool(judge["passed"])
        downgraded.append(
            {
                "example_id": example_id,
                "category": example.category,
                "unsupported_entities": unsupported,
                "judge_passed": judge_passed,
                "strict_match": strict_passed,
                "passes_both": judge_passed and strict_passed,
            }
        )

    summary = {
        "rows": len(rows),
        "answered_rows": answered_rows,
        "already_abstained_rows": len(rows) - answered_rows,
        "downgraded_rows": len(downgraded),
        "false_positive_rows": sum(row["passes_both"] for row in downgraded),
    }
    return summary, downgraded


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text())
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"expected top-level list of answer objects: {path}")
    return value


def run(golden_path: Path, output: Path) -> dict[str, Any]:
    golden = load_golden_set(golden_path)
    expected_golden_hash = golden_hash(golden_path)
    sources: list[dict[str, Any]] = []
    false_positives: list[dict[str, Any]] = []
    total_rows = 0
    total_downgraded = 0

    for answers_path in committed_answer_paths():
        manifest_path = answers_path.with_name(
            answers_path.name.removesuffix("_answers.json") + ".json"
        )
        if not manifest_path.exists():
            raise FileNotFoundError(f"source manifest is missing: {manifest_path}")
        manifest = _load_object(manifest_path)
        run_id = manifest.get("run_id")
        if run_id != answers_path.name.removesuffix("_answers.json"):
            raise ValueError(f"manifest/file run id mismatch: {manifest_path}")
        if manifest.get("variant") != "B_hybrid":
            raise ValueError(f"non-B_hybrid manifest entered replay: {manifest_path}")
        if manifest.get("golden_set_hash") != expected_golden_hash:
            raise ValueError(f"golden-set hash mismatch: {manifest_path}")

        summary, downgraded = replay_rows(_load_rows(answers_path), golden.examples)
        total_rows += summary["rows"]
        total_downgraded += summary["downgraded_rows"]
        source = {
            "run_id": run_id,
            "model": manifest.get("model"),
            "decoding": manifest.get("decoding"),
            "prompt_sha256": manifest.get("prompt_sha256"),
            "manifest_path": str(manifest_path.relative_to(REPO_ROOT)),
            "manifest_sha256": _sha256(manifest_path),
            "answers_path": str(answers_path.relative_to(REPO_ROOT)),
            "answers_sha256": _sha256(answers_path),
            **summary,
            "downgraded": downgraded,
        }
        sources.append(source)
        false_positives.extend(
            {"run_id": run_id, **row} for row in downgraded if row["passes_both"]
        )

    candidate_sources = [source for source in sources if source["run_id"] == CANDIDATE_RUN_ID]
    if len(candidate_sources) != 1:
        raise ValueError(f"expected exactly one candidate source, found {len(candidate_sources)}")
    candidate_defect_rows = [
        row
        for row in candidate_sources[0]["downgraded"]
        if row["example_id"] == CANDIDATE_DEFECT_ROW
    ]
    gate_1_passed = not false_positives
    gate_2_passed = len(candidate_defect_rows) == 1
    receipt = {
        "receipt": "support_coverage_replay_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git("rev-parse", "HEAD"),
        "config_hash": _sha256(CONFIG_PATH),
        "golden_set_hash": expected_golden_hash,
        "source_files": len(sources),
        "rows_replayed": total_rows,
        "rows_downgraded": total_downgraded,
        "gate_1_zero_false_positives": {
            "passed": gate_1_passed,
            "retracted_correct_rows": false_positives,
        },
        "gate_2_candidate_gs_005": {
            "passed": gate_2_passed,
            "run_id": CANDIDATE_RUN_ID,
            "rows": candidate_defect_rows,
        },
        "sources": sources,
        "interpretation_boundary": (
            "Deterministic replay over stored final answers and surviving citation "
            "snippets; zero generation calls. It predicts retractions, not live model "
            "behaviour. Gate 2 is a contaminated sanity check; generalisation rests "
            "on gate 1 across the preregistered historical population."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.golden, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
