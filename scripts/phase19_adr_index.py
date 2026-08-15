"""Phase 19 ADR index, generated from the files in `decisions/`.

SPEC asks for at least eight numbered decisions to remain traceable. Counting
them is the easy half. The hard half is that every ADR in this repository has
`Status: accepted`, because "accepted" describes the *decision*, not the
*outcome* — and an index that prints only that column would quietly turn two
waivers, two null results and two rejected candidates into a wall of successes.

So this index carries a second axis. Identity facts — number, title, date, the
status line, cross-references — are parsed from each file. The outcome class and
the one-line summary of what a decision actually records are declared in
`CLASSIFICATIONS` below, reviewable in source and asserted against the directory:
add an ADR without classifying it and this script fails rather than silently
dropping it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vaultledger.config import REPO_ROOT

DECISIONS_DIR = REPO_ROOT / "decisions"
DEFAULT_REPORT = REPO_ROOT / "reports" / "adr_index.md"
DEFAULT_RECEIPT = REPO_ROOT / "receipts" / "phase19_adr_index.json"

#: SPEC 16's traceability floor.
MINIMUM_DECISIONS = 8

_TITLE = re.compile(r"^#\s*ADR-(\d{4}):\s*(.+?)\s*$")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
# The newline exclusion is load-bearing. ADR-0001 and ADR-0002 write an unbolded
# `Status: accepted`, so without it the class runs past the end of the header
# line and drags the next section into a table cell.
_STATUS = re.compile(r"Status:?\s*\**\s*([^*·(\n]+)")
_REFERENCE = re.compile(r"ADR-(\d{4})")

#: Outcome classes, ordered from "this went as planned" to "this did not".
#: The order is the reading order of the summary table; it is not a ranking of
#: importance, and a decision is not worth less for landing lower down.
OUTCOME_ORDER: tuple[str, ...] = (
    "design choice",
    "measurement decision",
    "preregistration",
    "scope reduction",
    "null result",
    "rejected candidate",
    "waiver",
)

#: Classes that must never be summarised as the build succeeding at something.
NOT_A_SUCCESS: frozenset[str] = frozenset(
    {"scope reduction", "null result", "rejected candidate", "waiver"}
)


@dataclass(frozen=True)
class Classification:
    outcome: str
    records: str
    owed: str = ""


CLASSIFICATIONS: dict[int, Classification] = {
    1: Classification(
        "design choice",
        "Took the SPEC 7.1 defaults for the Phase 0 stack: Python 3.11, Streamlit, "
        "Pydantic v2, one `config.yaml`.",
    ),
    2: Classification(
        "design choice",
        "Native structured output plus a hand-rolled bounded repair loop, with citation "
        "verification against retrieved chunks.",
    ),
    3: Classification(
        "scope reduction",
        "Dropped the paid hosted tiers for a local-only lineup, replacing the cost axis "
        "with a resource axis.",
        owed="SPEC §19's three-tier Kimi/GLM clause is not met and is not claimed.",
    ),
    4: Classification(
        "design choice",
        "Deterministic size-policy router first; a learned router is deferred until more "
        "than one labelled evaluation set exists.",
    ),
    5: Classification(
        "design choice",
        "Custom-first guardrails plus an offline captured-payload egress contract, with no "
        "cloud path.",
    ),
    6: Classification(
        "design choice",
        "Variant D's agent loop is hand-rolled and bounded rather than LangGraph.",
    ),
    7: Classification(
        "design choice",
        "Added a wall-clock budget to the bounded loop and required every generator to "
        "decode like the eval gateway.",
    ),
    8: Classification(
        "design choice",
        "LightRAG through a narrow adapter with local NetworkX storage; Obsidian is a "
        "projection, never the store.",
    ),
    9: Classification(
        "measurement decision",
        "Defined the account-alias rule as a named *secondary* metric and fixed the "
        "precision convention as distinct expected entities over unique extracted nodes.",
        owed="The post-hoc alias rule was written after seeing the strict result, so the "
        "headline stays 11/15 = 73.3% and the gate stays missed.",
    ),
    10: Classification(
        "waiver",
        "Waived Phase 15's preregistered entity-recall gate for one phase. The gate was "
        "measured and missed at 73.3% against 80%.",
        owed="Phase 15 closes as an implementation and evaluation milestone, never as an "
        "all-green acceptance result.",
    ),
    11: Classification(
        "design choice",
        "Re-sequenced the remaining phases to ship the product before judging it, and "
        "chose local distribution without a native shell.",
    ),
    12: Classification(
        "design choice",
        "OCR as an `ocrmypdf --skip-text` preprocessing step with provenance carried to "
        "the citation, because a citation cannot detect a misread digit.",
    ),
    13: Classification(
        "waiver",
        "Waived Phase 17's machine half, deferring it in full to a validation pass "
        "immediately before handoff. This waives an *unattempted* gate, which is weaker "
        "than ADR-0010's waiver of a measured one.",
        owed="Still owed before handoff: the fresh macOS Administrator-account install and "
        "its receipt, checklist items A5–A7, and an independent non-technical cold read.",
    ),
    14: Classification(
        "preregistration",
        "Fixed the decoding sweep's grid, population and decision rule before any sweep "
        "cell ran.",
    ),
    15: Classification(
        "design choice",
        "One shared Ollama `/api/chat` path for product and evaluation, so the two cannot "
        "drift apart.",
    ),
    16: Classification(
        "null result",
        "Retained `qwen3:8b` after a six-model paired bake-off. No alternative beat it; "
        "three were significantly worse; the two that tied cost 3.7–4.4× the median latency.",
        owed="Say 'measured against five alternatives; none beat it'. `p`=0.754 is absence "
        "of evidence, not equivalence.",
    ),
    17: Classification(
        "null result",
        "Retained `temperature=0.0 / top_p=0.95 / top_k=20`. No preregistered decoding cell "
        "met the rule; all seven profiles passed exactly the same 35 strict rows.",
    ),
    18: Classification(
        "preregistration",
        "Fixed one evidence-first prompt candidate, its frozen baseline, and its adoption "
        "thresholds before the candidate cell ran.",
    ),
    19: Classification(
        "rejected candidate",
        "Rejected the evidence-first prompt. Abstentions improved 19→15, but paired judge "
        "movement was 2 wins / 0 losses against a preregistered +4 gate.",
        owed="The original prompt is restored and no second candidate is permitted. Three "
        "of four newly answered rows only moved from `FALSE_ABSTAIN` to `INCORRECT`.",
    ),
    20: Classification(
        "preregistration",
        "Fixed the support-aware entity-coverage citation rule, its replay population and "
        "its zero-false-positive gate before any implementation existed.",
    ),
    21: Classification(
        "rejected candidate",
        "Rejected the entity-coverage verifier before any live cell. Replay over 1,040 "
        "committed rows predicted 96 downgrades including 28 that already passed both judge "
        "and strict scorer.",
        owed="The rule stays replay-only and must not be tuned on those rows or described "
        "as shipped. The underlying faithfulness defect is unfixed.",
    ),
    22: Classification(
        "rejected candidate",
        "Rejected the empty-SQL-result contract after its paired 26-row run fixed `mh_009` "
        "but lost five committed strict passes and produced one budget-exhaustion `TOOL_ERR`.",
        owed="The prior SQL summary and planner prompt are restored. Empty SQL results remain "
        "logically uninformative, and the demonstrated false-negative failure remains open.",
    ),
    23: Classification(
        "preregistration",
        "Retests the empty-SQL-result contract payload-only against a same-code baseline, "
        "after review found ADR-0022's two arms differed by three variables rather than one.",
        owed="Discharged by ADR-0024. ADR-0022's rejection remains set aside as untestable "
        "rather than being treated as evidence for the clean retest.",
    ),
    24: Classification(
        "rejected candidate",
        "Rejected the payload-only empty-result contract after `mh_011` lost a baseline "
        "strict pass and the candidate produced four budget-exhaustion `TOOL_ERR`s.",
        owed="The payload is restored, both experimental runs are excluded from product "
        "history, and there is no third wording attempt. The schema gap moves to Phase 20.",
    ),
}


@dataclass(frozen=True)
class Adr:
    number: int
    title: str
    date: str
    status: str
    path: str
    sha256: str
    references: tuple[int, ...]
    classification: Classification


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


def parse_adr(path: Path) -> tuple[int, str, str, str, tuple[int, ...]]:
    """Read one ADR's identity facts. Nothing here is inferred or supplied."""
    lines = path.read_text().splitlines()
    title_match = _TITLE.match(lines[0]) if lines else None
    if title_match is None:
        raise ValueError(f"{path.name} does not open with an `# ADR-NNNN: title` heading")
    number = int(title_match.group(1))
    title = title_match.group(2)

    header = "\n".join(lines[1:6])
    date_match = _DATE.search(header)
    if date_match is None:
        raise ValueError(f"{path.name} carries no date in its header block")
    status_match = _STATUS.search(header)
    if status_match is None:
        raise ValueError(f"{path.name} carries no `Status:` field in its header block")
    status = status_match.group(1).strip().rstrip(";,")
    references = tuple(
        sorted({int(ref) for ref in _REFERENCE.findall(header)} - {number})
    )
    return number, title, date_match.group(1), status, references


def load_adrs(directory: Path = DECISIONS_DIR) -> list[Adr]:
    """Load every numbered ADR, refusing to skip one that has no classification."""
    paths = sorted(path for path in directory.glob("ADR-0*.md") if path.name != "ADR-TEMPLATE.md")
    if not paths:
        raise FileNotFoundError(f"no numbered ADRs found in {directory}")

    adrs: list[Adr] = []
    for path in paths:
        number, title, date, status, references = parse_adr(path)
        classification = CLASSIFICATIONS.get(number)
        if classification is None:
            raise ValueError(
                f"ADR-{number:04d} has no entry in CLASSIFICATIONS. Classify it rather than "
                "letting the index render it as an unqualified acceptance."
            )
        if classification.outcome not in OUTCOME_ORDER:
            raise ValueError(
                f"ADR-{number:04d} uses unknown outcome {classification.outcome!r}"
            )
        adrs.append(
            Adr(
                number=number,
                title=title,
                date=date,
                status=status,
                path=str(path.relative_to(REPO_ROOT)),
                sha256=_sha256(path),
                references=references,
                classification=classification,
            )
        )

    declared = set(CLASSIFICATIONS)
    found = {adr.number for adr in adrs}
    if declared - found:
        missing = ", ".join(f"ADR-{number:04d}" for number in sorted(declared - found))
        raise ValueError(f"CLASSIFICATIONS names decisions with no file: {missing}")
    return sorted(adrs, key=lambda adr: adr.number)


_OUTCOME_VERBS: dict[str, tuple[str, str]] = {
    "waiver": ("waives a gate", "waive a gate"),
    "null result": ("records a null result", "record a null result"),
    "rejected candidate": (
        "rejects a candidate the build had already implemented",
        "reject a candidate the build had already implemented",
    ),
    "scope reduction": ("reduces the shipped scope", "reduce the shipped scope"),
}

_COUNT_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def _outcome_phrase(by_outcome: dict[str, list[Adr]]) -> str:
    """Describe the not-a-success classes from the counted files, not from memory."""
    clauses: list[str] = []
    for outcome, (singular, plural) in _OUTCOME_VERBS.items():
        count = len(by_outcome.get(outcome, []))
        if not count:
            continue
        word = _COUNT_WORDS.get(count, str(count))
        verb = singular if count == 1 else plural
        clauses.append(f"{word.casefold()} {verb}")
    if not clauses:
        return "Every decision here records something the build went on to keep"
    if len(clauses) == 1:
        body = clauses[0]
    else:
        body = ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
    return "Of these decisions, " + body


def build_report(directory: Path = DECISIONS_DIR) -> tuple[str, dict]:
    adrs = load_adrs(directory)
    generated_at = datetime.now(UTC).isoformat()
    git_sha = _git("rev-parse", "HEAD")
    by_outcome: dict[str, list[Adr]] = {outcome: [] for outcome in OUTCOME_ORDER}
    for adr in adrs:
        by_outcome[adr.classification.outcome].append(adr)
    not_success = [adr for adr in adrs if adr.classification.outcome in NOT_A_SUCCESS]
    superseded = [adr for adr in adrs if "supersed" in adr.status.casefold()]

    lines = [
        "# Decision index",
        "",
        "Generated by `python -m scripts.phase19_adr_index`. **Never hand-edited.** Number, "
        "title, date, status and cross-references are parsed from each file in `decisions/`; "
        "the outcome class and the one-line summary are declared in the generator and "
        "checked against the directory, so an unclassified ADR fails the run instead of "
        "appearing as an unqualified acceptance.",
        "",
        f"Repo `{git_sha[:12]}` · {len(adrs)} numbered decisions · generated {generated_at}",
        "",
        "## Why there are two status columns",
        "",
        "Every ADR here reads `Status: accepted`, and on its own that column is misleading. "
        "`accepted` describes the **decision** — the owner made this call and the repository "
        "follows it. It says nothing about whether the thing decided *worked*. "
        + _outcome_phrase(by_outcome)
        + ".",
        "",
        f"`Records` is that second axis. **{len(not_success)} of {len(adrs)}** decisions "
        "record something other than a success, and they are listed again in full below so "
        "the count cannot be read past.",
        "",
        "## Outcome summary",
        "",
        "| Outcome | Count | Decisions |",
        "|---|---:|---|",
    ]
    for outcome in OUTCOME_ORDER:
        members = by_outcome[outcome]
        if not members:
            continue
        ids = ", ".join(f"ADR-{adr.number:04d}" for adr in members)
        lines.append(f"| {outcome} | {len(members)} | {ids} |")

    lines.extend(
        [
            "",
            f"SPEC's traceability floor is {MINIMUM_DECISIONS} numbered decisions. "
            f"There are **{len(adrs)}**, so the floor is met. Meeting a count is not "
            "evidence that the decisions were good ones.",
            "",
            "## The index",
            "",
            "| ADR | Date | Title | Status | Outcome | What it records |",
            "|---|---|---|---|---|---|",
        ]
    )
    for adr in adrs:
        lines.append(
            f"| [`ADR-{adr.number:04d}`]({Path(adr.path).relative_to('decisions').as_posix()}) "
            f"| {adr.date} | {adr.title} | {adr.status} | {adr.classification.outcome} "
            f"| {adr.classification.records} |"
        )

    lines.extend(
        [
            "",
            "The links are relative to `decisions/`, which is where this index is read from "
            "when it travels with the repository.",
            "",
            "## Decisions that are not successes",
            "",
            "Each of these is a real result and belongs in the record. None of them may be "
            "summarised as the build succeeding at the thing the decision is about.",
            "",
        ]
    )
    for adr in not_success:
        lines.extend(
            [
                f"**ADR-{adr.number:04d} — {adr.title}** · {adr.classification.outcome}",
                "",
                f"{adr.classification.records}",
                "",
            ]
        )
        if adr.classification.owed:
            lines.extend([f"*Constraint or debt:* {adr.classification.owed}", ""])

    lines.extend(
        [
            "## Chains: which decision discharges which",
            "",
            "Parsed from each ADR's header block. A preregistration is only worth its name "
            "if a later decision applies its rule without changing it, so these pairs are "
            "the part of the record that shows the rule was fixed in advance.",
            "",
            "| Decision | References |",
            "|---|---|",
        ]
    )
    chained = [adr for adr in adrs if adr.references]
    for adr in chained:
        refs = ", ".join(f"ADR-{number:04d}" for number in adr.references)
        lines.append(f"| `ADR-{adr.number:04d}` | {refs} |")
    if not chained:
        lines.append("| — | no ADR header cross-references another |")

    lines.extend(
        [
            "",
            "## Supersession",
            "",
            (
                "No ADR in this repository is marked superseded. Every numbered decision is "
                "still in force as written, including the ones that record a null, a "
                "rejection or a waiver."
                if not superseded
                else "Superseded decisions: "
                + ", ".join(f"`ADR-{adr.number:04d}`" for adr in superseded)
                + "."
            ),
            "",
            "## What this index does not claim",
            "",
            "It does not claim the decisions were correct, that the waived gates were later "
            "met, or that a rejected candidate can be revisited. ADR-0010 waives a gate that "
            "was measured and missed; ADR-0013 waives one that was never attempted, which is "
            "weaker; and the Phase 17 machine half remains owed rather than done.",
        ]
    )

    receipt = {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "decision_count": len(adrs),
        "minimum_decisions": MINIMUM_DECISIONS,
        "meets_minimum": len(adrs) >= MINIMUM_DECISIONS,
        "not_a_success_count": len(not_success),
        "outcomes": {
            outcome: [adr.number for adr in by_outcome[outcome]]
            for outcome in OUTCOME_ORDER
            if by_outcome[outcome]
        },
        "decisions": [
            {
                "number": adr.number,
                "title": adr.title,
                "date": adr.date,
                "status": adr.status,
                "path": adr.path,
                "sha256": adr.sha256,
                "references": list(adr.references),
                "outcome": adr.classification.outcome,
                "owed": adr.classification.owed,
            }
            for adr in adrs
        ],
    }
    return "\n".join(lines) + "\n", receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.phase19_adr_index")
    parser.add_argument("--decisions", default=str(DECISIONS_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT))
    args = parser.parse_args(argv)

    text, receipt = build_report(Path(args.decisions))
    report_path = Path(args.report)
    receipt_path = Path(args.receipt)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"decision index: {report_path} ({receipt['decision_count']} decisions)")
    print(f"receipt: {receipt_path}")
    print(f"not-a-success decisions: {receipt['not_a_success_count']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
