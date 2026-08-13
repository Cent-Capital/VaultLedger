"""Versioned LLM-judge rubric and human-label validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel

JUDGE_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS_PATH = JUDGE_DIR / "human_labels.yaml"
DEFAULT_RUBRIC_PATH = JUDGE_DIR / "rubric_v1.md"


class JudgeItem(BaseModel):
    id: str
    question: str
    reference_answer: str
    evidence: str
    candidate_answer: str
    human_pass: bool


class JudgeVerdict(BaseModel):
    passed: bool
    reason: str
    failure_code: Literal[
        "NONE",
        "INCORRECT",
        "UNSUPPORTED",
        "FALSE_ABSTAIN",
        "INJECTION",
        "OTHER",
    ]


class JudgeGenerator(Protocol):
    def generate_json(
        self, prompt: str, schema: dict, *, temperature: float | None = None
    ) -> str: ...


def load_human_labels(path: str | Path = DEFAULT_LABELS_PATH) -> list[JudgeItem]:
    payload = yaml.safe_load(Path(path).read_text())
    items = [JudgeItem.model_validate(item) for item in payload["items"]]
    if len(items) != 20:
        raise ValueError(f"judge validation requires exactly 20 labels, got {len(items)}")
    positives = sum(item.human_pass for item in items)
    if positives != 10:
        raise ValueError(f"judge validation must be balanced 10/10, got {positives}/20")
    if len({item.id for item in items}) != len(items):
        raise ValueError("judge validation ids must be unique")
    return items


def rubric_hash(path: str | Path = DEFAULT_RUBRIC_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_judge_prompt(item: JudgeItem, rubric: str) -> str:
    return f"""You are validating a financial-document Q&A answer.

{rubric}

QUESTION:
{item.question}

REFERENCE ANSWER:
{item.reference_answer}

SUPPORTING EVIDENCE:
{item.evidence}

CANDIDATE ANSWER:
{item.candidate_answer}

VERDICT JSON:"""


def judge_item(
    generator: JudgeGenerator,
    item: JudgeItem,
    *,
    rubric_path: str | Path = DEFAULT_RUBRIC_PATH,
) -> JudgeVerdict:
    rubric = Path(rubric_path).read_text()
    raw = generator.generate_json(
        build_judge_prompt(item, rubric),
        JudgeVerdict.model_json_schema(),
    )
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"judge returned non-JSON for {item.id}")
    return JudgeVerdict.model_validate(json.loads(raw[start : end + 1]))


def validation_metrics(
    items: list[JudgeItem],
    verdicts: dict[str, JudgeVerdict],
) -> tuple[dict[str, float], list[dict]]:
    tp = tn = fp = fn = 0
    failures: list[dict] = []
    for item in items:
        verdict = verdicts[item.id]
        if item.human_pass and verdict.passed:
            tp += 1
        elif item.human_pass:
            fn += 1
        elif verdict.passed:
            fp += 1
        else:
            tn += 1
        if verdict.passed != item.human_pass:
            failures.append(
                {
                    "example_id": item.id,
                    "taxonomy_code": "TOOL_ERR",
                    "note": (
                        f"judge={verdict.passed}, human={item.human_pass}: "
                        f"{verdict.reason}"
                    ),
                }
            )
    return {
        "judge_tpr": tp / (tp + fn),
        "judge_tnr": tn / (tn + fp),
        "judge_accuracy": (tp + tn) / len(items),
        "judge_tp": float(tp),
        "judge_tn": float(tn),
        "judge_fp": float(fp),
        "judge_fn": float(fn),
        "judge_validation_n": float(len(items)),
    }, failures


__all__ = [
    "DEFAULT_LABELS_PATH",
    "DEFAULT_RUBRIC_PATH",
    "JudgeItem",
    "JudgeVerdict",
    "build_judge_prompt",
    "judge_item",
    "load_human_labels",
    "rubric_hash",
    "validation_metrics",
]
