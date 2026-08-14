"""Phase 19 failure-taxonomy Pareto sequence, discovered from committed receipts.

SPEC's portfolio phase asks for a Pareto of failure categories shrinking across
the build. This module refuses to produce that picture by selection. It finds
every historical snapshot that is genuinely comparable, renders them in order,
and then **computes** whether the bars actually shrink instead of asserting it.

Comparability is a rule, not a judgement call. Two snapshots may sit in one
sequence only when they share variant, model, golden-set hash and row
population, and only when both ran the shipped prompt and the shipped decoding
profile. Anything else is excluded by name and reason, so a reader can see what
was left out rather than infer it from a gap.

The pipeline configuration is allowed to differ inside a sequence — that is what
makes it a history rather than an A/B — but it is printed on every row, because
a bar that moves between two config hashes carries pipeline drift as well as
model behaviour.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from argparse import Namespace
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from vaultledger.config import REPO_ROOT, load_config
from vaultledger.evals.matrix import _config_hash, _git_sha
from vaultledger.generate.reliable import PROMPT_SHA256
from vaultledger.schemas import RunManifest

DEFAULT_REPORT = REPO_ROOT / "reports" / "failure_pareto.md"
DEFAULT_CHART_DIR = REPO_ROOT / "reports" / "paretos"
DEFAULT_RECEIPT = REPO_ROOT / "receipts" / "phase19_failure_pareto.json"

#: A sequence needs at least this many comparable snapshots to be drawn at all.
MIN_SEQUENCE = 3

#: SPEC's failure taxonomy, with the reading each code supports. Codes are
#: printed in this order everywhere so two charts can be compared by eye.
TAXONOMY: tuple[tuple[str, str], ...] = (
    ("ABSTAIN_FP", "abstained on a row the golden set marks answerable"),
    ("ABSTAIN_FN", "answered a row the golden set marks unanswerable"),
    ("NUM_MISMATCH", "a reference quantity is missing from the answer or differs beyond epsilon"),
    ("GEN_HALLUC", "the answer failed the deterministic literal-anchor check"),
    ("CITE_FAIL", "no citation survived verification against the retrieved chunks"),
    ("RANK_MISS", "an expected document was absent from the retrieved top-k"),
    ("TOOL_ERR", "the row produced no answer: transport, budget or loop failure"),
)

TAXONOMY_COLOURS: dict[str, str] = {
    "ABSTAIN_FP": "#2563eb",
    "ABSTAIN_FN": "#7c3aed",
    "NUM_MISMATCH": "#d97706",
    "GEN_HALLUC": "#dc2626",
    "CITE_FAIL": "#0891b2",
    "RANK_MISS": "#65a30d",
    "TOOL_ERR": "#6b7280",
}


@dataclass(frozen=True)
class Snapshot:
    """One measured cell, reduced to its failure histogram."""

    run_id: str
    relative_path: str
    timestamp: str
    config_hash: str
    rows: int
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def date(self) -> str:
        return self.timestamp[:10]


@dataclass
class Group:
    """Every snapshot sharing one comparable arm."""

    variant: str
    model: str
    rows: int
    golden_set_hash: str
    #: Every committed run in the arm, before the one-per-config rule.
    all_snapshots: list[Snapshot] = field(default_factory=list)
    #: What the sequence actually draws: one snapshot per pipeline config.
    snapshots: list[Snapshot] = field(default_factory=list)

    @property
    def key(self) -> str:
        model_slug = self.model.replace("/", "_").replace(":", "_").replace(".", "p")
        return f"{self.variant.casefold()}_{model_slug}_{self.rows}"

    @property
    def label(self) -> str:
        return f"`{self.variant}` · `{self.model}` · {self.rows} rows"

    @property
    def is_sequence(self) -> bool:
        return len(self.snapshots) >= MIN_SEQUENCE


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


def _committed_manifest_paths() -> list[str]:
    skip = ("_answers.json", "_answer.json", "_details.json", "_verdicts.json")
    return [
        line
        for line in _git("ls-files", "--", "reports").splitlines()
        if line.endswith(".json") and not line.endswith(skip)
    ]


def collect_groups(
    *,
    shipped_temperature: float,
    shipped_top_p: float,
) -> tuple[list[Group], list[tuple[str, str, str]]]:
    """Discover comparable snapshot sequences and the runs excluded from them.

    Returns ``(groups, exclusions)`` where each exclusion is
    ``(run_id, relative_path, reason)``. Nothing is hand-selected: a snapshot
    enters a group by satisfying the rule, and every rejection carries a reason
    that names the run.
    """
    grouped: dict[tuple[str, str, int, str], Group] = {}
    exclusions: list[tuple[str, str, str]] = []
    seen_run_ids: dict[str, str] = {}

    for relative in sorted(_committed_manifest_paths()):
        try:
            manifest = RunManifest.model_validate_json((REPO_ROOT / relative).read_text())
        except ValueError:
            continue
        rows = manifest.metrics.get("matrix_examples")
        if rows is None:
            # Retrieval-only and guardrail receipts carry a different population
            # and a different taxonomy; they are reported separately, not mixed
            # into a generation Pareto.
            continue

        if manifest.run_id in seen_run_ids:
            # `*_latest.json` pointers are byte copies of a dated manifest.
            continue
        seen_run_ids[manifest.run_id] = relative

        if manifest.prompt_sha256 is not None and manifest.prompt_sha256 != PROMPT_SHA256:
            exclusions.append(
                (
                    manifest.run_id,
                    relative,
                    "ran a prompt the product does not ship (ADR-0019 rejected candidate)",
                )
            )
            continue

        decoding = manifest.decoding
        if decoding is not None and (
            decoding.temperature != shipped_temperature or decoding.top_p != shipped_top_p
        ):
            exclusions.append(
                (
                    manifest.run_id,
                    relative,
                    f"decoding sweep arm at t={decoding.temperature:g}/p={decoding.top_p:g}, "
                    "not the shipped profile",
                )
            )
            continue

        snapshot = Snapshot(
            run_id=manifest.run_id,
            relative_path=relative,
            timestamp=manifest.timestamp,
            config_hash=manifest.config_hash,
            rows=int(rows),
            counts=dict(
                Counter(
                    str(failure.get("taxonomy_code", "UNKNOWN"))
                    for failure in manifest.failures
                )
            ),
        )
        key = (manifest.variant, manifest.model, int(rows), manifest.golden_set_hash)
        group = grouped.setdefault(
            key,
            Group(
                variant=manifest.variant,
                model=manifest.model,
                rows=int(rows),
                golden_set_hash=manifest.golden_set_hash,
            ),
        )
        group.all_snapshots.append(snapshot)

    for group in grouped.values():
        # One snapshot per pipeline configuration, earliest first. Re-runs at the
        # same config are repetitions, not history, and counting them would let a
        # flat sequence look like three data points.
        by_config: dict[str, Snapshot] = {}
        for snapshot in sorted(group.all_snapshots, key=lambda item: item.timestamp):
            by_config.setdefault(snapshot.config_hash, snapshot)
        group.all_snapshots = sorted(group.all_snapshots, key=lambda item: item.timestamp)
        group.snapshots = sorted(by_config.values(), key=lambda item: item.timestamp)

    ordered = sorted(
        grouped.values(),
        key=lambda group: (-len(group.snapshots), group.variant, group.model, -group.rows),
    )
    return ordered, exclusions


def sequence_verdict(group: Group) -> dict[str, object]:
    """Compute, never assert, whether this sequence's bars actually shrink."""
    totals = [snapshot.total for snapshot in group.snapshots]
    codes = sorted({code for snapshot in group.snapshots for code in snapshot.counts})
    shrinking_codes = []
    growing_codes = []
    for code in codes:
        series = [snapshot.counts.get(code, 0) for snapshot in group.snapshots]
        if series[-1] < series[0]:
            shrinking_codes.append(code)
        elif series[-1] > series[0]:
            growing_codes.append(code)
    return {
        "totals": totals,
        "total_change": totals[-1] - totals[0],
        # Deliberately not strict: the two operands are offset by one by
        # construction. `strict=True` here raises only when every pair compares
        # true, so it would fail exactly on the sequence this artifact exists to
        # report — a genuinely shrinking one.
        "monotonic_decrease": all(b < a for a, b in zip(totals, totals[1:], strict=False)),
        "net_decrease": totals[-1] < totals[0],
        "shrinking_codes": shrinking_codes,
        "growing_codes": growing_codes,
        "dominant_first": max(group.snapshots[0].counts, key=group.snapshots[0].counts.get)
        if group.snapshots[0].counts
        else None,
        "dominant_last": max(group.snapshots[-1].counts, key=group.snapshots[-1].counts.get)
        if group.snapshots[-1].counts
        else None,
    }


def _verdict_sentences(group: Group, verdict: dict[str, object]) -> list[str]:
    totals = verdict["totals"]
    trail = " → ".join(str(total) for total in totals)
    lines = [f"Total scored failures across the sequence: **{trail}**."]
    if verdict["monotonic_decrease"]:
        lines.append(
            "The bars shrink at every step. SPEC's requested picture is supported for this arm."
        )
    elif verdict["net_decrease"]:
        lines.append(
            "The last snapshot carries fewer failures than the first, but not at every step, "
            "so this is a net decrease and not a shrinking-bars sequence."
        )
    else:
        change = verdict["total_change"]
        lines.append(
            f"The total moved by **{change:+d}** across the whole sequence, so **the requested "
            "shrinking-bars story is not supported for this arm**. What changed is the "
            "composition, not the height."
        )
    if verdict["shrinking_codes"] or verdict["growing_codes"]:
        shrank = ", ".join(f"`{code}`" for code in verdict["shrinking_codes"]) or "none"
        grew = ", ".join(f"`{code}`" for code in verdict["growing_codes"]) or "none"
        lines.append(f"Categories that fell end to end: {shrank}. Categories that rose: {grew}.")
    first, last = verdict["dominant_first"], verdict["dominant_last"]
    if first and last:
        if first == last:
            lines.append(f"The largest single failure category stayed `{first}` throughout.")
        else:
            lines.append(
                f"The largest single failure category moved from `{first}` to `{last}`."
            )
    return lines


def write_chart(group: Group, output_path: Path) -> None:
    """Render one sequence as grouped bars, with the caveat inside the image."""
    snapshots = group.snapshots
    codes = [code for code, _ in TAXONOMY if any(s.counts.get(code) for s in snapshots)]
    width, height = 1120, 640
    left, right, top, bottom = 90, 250, 120, 150
    plot_width = width - left - right
    plot_height = height - top - bottom
    peak = max(
        (snapshot.counts.get(code, 0) for snapshot in snapshots for code in codes),
        default=1,
    )
    peak = max(peak, 1)
    slot = plot_width / max(len(codes), 1)
    bar_width = min(26.0, (slot - 18) / max(len(snapshots), 1))

    svg = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            '<style>text{font-family:Inter,Arial,sans-serif;fill:#172033}'
            '.mono{font-family:ui-monospace,SFMono-Regular,monospace}'
            '.muted{fill:#667085}.grid{stroke:#e5e7eb;stroke-width:1}'
            '.axis{stroke:#344054;stroke-width:1.3}</style>'
        ),
        (
            '<text x="90" y="38" font-size="22" font-weight="700">'
            f'Failure taxonomy over time — {escape(group.variant)} · '
            f'{escape(group.model)}</text>'
        ),
        (
            f'<text x="90" y="64" font-size="13" class="muted">{len(snapshots)} snapshots · '
            f'{group.rows} rows each · one snapshot per pipeline config · '
            'counts, not rates</text>'
        ),
        (
            f'<text x="90" y="86" font-size="13" class="muted">Bars are absolute failure counts '
            f'out of {group.rows} scored rows. A row can fail more than one check, so the '
            'categories do not sum to the row count.</text>'
        ),
    ]

    steps = 4
    for index in range(steps + 1):
        value = peak * index / steps
        y = top + plot_height - (value / peak) * plot_height
        svg.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
                'class="grid"/>',
                f'<text x="{left - 14}" y="{y + 4:.1f}" font-size="12" class="muted" '
                f'text-anchor="end">{value:.0f}</text>',
            ]
        )
    svg.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" class="axis"/>'
    )

    for code_index, code in enumerate(codes):
        base = left + code_index * slot
        for snap_index, snapshot in enumerate(snapshots):
            count = snapshot.counts.get(code, 0)
            bar_height = (count / peak) * plot_height
            x = base + 9 + snap_index * (bar_width + 3)
            y = top + plot_height - bar_height
            opacity = 0.35 + 0.65 * (snap_index / max(len(snapshots) - 1, 1))
            svg.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                f'height="{bar_height:.1f}" fill="{TAXONOMY_COLOURS.get(code, "#334155")}" '
                f'fill-opacity="{opacity:.2f}" rx="2"/>'
            )
            if count:
                svg.append(
                    f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" font-size="11" '
                    f'text-anchor="middle" class="muted">{count}</text>'
                )
        svg.append(
            f'<text x="{base + slot / 2:.1f}" y="{top + plot_height + 24}" font-size="12" '
            f'text-anchor="middle" class="mono">{escape(code)}</text>'
        )

    legend_x = left + plot_width + 34
    svg.append(
        f'<text x="{legend_x}" y="{top + 6}" font-size="12" font-weight="700">Snapshot</text>'
    )
    for snap_index, snapshot in enumerate(snapshots):
        opacity = 0.35 + 0.65 * (snap_index / max(len(snapshots) - 1, 1))
        row_y = top + 26 + snap_index * 40
        svg.extend(
            [
                f'<rect x="{legend_x}" y="{row_y - 10}" width="14" height="14" '
                f'fill="#334155" fill-opacity="{opacity:.2f}" rx="2"/>',
                f'<text x="{legend_x + 22}" y="{row_y + 2}" font-size="12">'
                f'{escape(snapshot.date)}</text>',
                f'<text x="{legend_x + 22}" y="{row_y + 18}" font-size="10" class="mono muted">'
                f'cfg {escape(snapshot.config_hash[:8])} · {snapshot.total} total</text>',
            ]
        )

    caveat_y = height - 96
    svg.extend(
        [
            f'<rect x="70" y="{caveat_y}" width="{width - 140}" height="76" rx="8" '
            'fill="#fff7ed" stroke="#fdba74"/>',
            f'<text x="90" y="{caveat_y + 24}" font-size="12" font-weight="700">'
            'Read the config hashes before reading the trend</text>',
            f'<text x="90" y="{caveat_y + 44}" font-size="11" class="muted">'
            'Each snapshot ran under a different pipeline configuration, so a bar that moves '
            'carries pipeline drift as well as model behaviour.</text>',
            f'<text x="90" y="{caveat_y + 62}" font-size="11" class="muted">'
            'Counts are single runs, not repeated measurements: no error bar is available and '
            'a small move is not a demonstrated improvement.</text>',
        ]
    )
    svg.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(svg) + "\n")


def build_report(*, chart_dir: Path = DEFAULT_CHART_DIR) -> tuple[str, dict]:
    chart_dir = chart_dir if chart_dir.is_absolute() else (REPO_ROOT / chart_dir)
    cfg = load_config()
    groups, exclusions = collect_groups(
        shipped_temperature=cfg.generation.temperature,
        shipped_top_p=cfg.generation.top_p,
    )
    sequences = [group for group in groups if group.is_sequence]
    generated_at = datetime.now(UTC).isoformat()
    git_sha = _git_sha()

    lines = [
        "# Failure-taxonomy Pareto sequence",
        "",
        "Generated by `python -m vaultledger.evals failure-pareto`. **Never hand-edited.** "
        "No cell is run here and no model is called: every count is the length of a "
        "`failures` array in a committed run manifest.",
        "",
        f"Repo `{git_sha[:12]}` · config `{_config_hash()[:12]}` · generated {generated_at}",
        "",
        "## The comparability rule",
        "",
        "SPEC asks for failure categories shrinking across the build. That picture is easy to "
        "manufacture by choosing snapshots, so the snapshots here are **discovered by rule** "
        "and the trend is **computed** rather than described.",
        "",
        "Two snapshots may share a sequence only when all four match: variant, model, "
        "golden-set hash, and row population. Both must also have run the shipped prompt and "
        "the shipped decoding profile "
        f"(`t={cfg.generation.temperature:g}`, `p={cfg.generation.top_p:g}`); receipts written "
        "before decoding was recorded qualify because "
        "`receipts/phase18_decoding_defaults.json` establishes that the implicit values were "
        "the ones later promoted to config.",
        "",
        "Within a sequence the pipeline **configuration is allowed to differ** — that is what "
        "makes it a history instead of an A/B — and exactly one snapshot is kept per config "
        "hash, the earliest. Re-runs at one config are repetitions, not history, and letting "
        "them in would pad a flat sequence into a full-looking chart.",
        "",
        f"A sequence needs at least **{MIN_SEQUENCE}** snapshots to be drawn.",
        "",
    ]

    receipt_sequences: dict[str, dict] = {}

    if not sequences:
        lines.extend(
            [
                "## No sequence is supported",
                "",
                "No arm reached the minimum snapshot count under the rule above. The coverage "
                "table below is the complete finding; the requested shrinking-bars chart is "
                "not supported by this repository's receipts.",
                "",
            ]
        )

    for index, group in enumerate(sequences, start=1):
        verdict = sequence_verdict(group)
        chart_path = (chart_dir / f"failure_pareto_{group.key}.svg").resolve()
        write_chart(group, chart_path)
        try:
            chart_ref = chart_path.relative_to(DEFAULT_REPORT.parent)
        except ValueError:  # pragma: no cover - defensive, chart dir is under reports/
            chart_ref = chart_path
        codes = [code for code, _ in TAXONOMY if any(s.counts.get(code) for s in group.snapshots)]
        lines.extend(
            [
                f"## Sequence {index}: {group.label}",
                "",
                f"![Failure taxonomy over time]({chart_ref})",
                "",
                "| Snapshot | Date | Config hash | Rows | "
                + " | ".join(f"`{code}`" for code in codes)
                + " | Total |",
                "|---|---|---|---:|"
                + "".join("---:|" for _ in codes)
                + "---:|",
            ]
        )
        for snapshot in group.snapshots:
            counts = " | ".join(str(snapshot.counts.get(code, 0)) for code in codes)
            lines.append(
                f"| `{snapshot.run_id}` | {snapshot.date} | `{snapshot.config_hash[:12]}` | "
                f"{snapshot.rows} | {counts} | **{snapshot.total}** |"
            )
        lines.append("")
        lines.extend(_verdict_sentences(group, verdict))
        lines.extend(
            [
                "",
                "A row can trip more than one check, so the categories do not sum to the row "
                "count and the total is a count of findings rather than of failed rows. Each "
                "snapshot is a single run with no repeat measurement, so a move of one or two "
                "counts is inside the noise this build cannot resolve.",
                "",
            ]
        )
        receipt_sequences[group.key] = {
            "variant": group.variant,
            "model": group.model,
            "rows": group.rows,
            "chart": str(chart_path.relative_to(REPO_ROOT)),
            "snapshots": [
                {
                    "run_id": snapshot.run_id,
                    "path": snapshot.relative_path,
                    "sha256": _sha256(REPO_ROOT / snapshot.relative_path),
                    "timestamp": snapshot.timestamp,
                    "config_hash": snapshot.config_hash,
                    "rows": snapshot.rows,
                    "counts": snapshot.counts,
                    "total": snapshot.total,
                }
                for snapshot in group.snapshots
            ],
            "verdict": verdict,
        }

    lines.extend(
        [
            "## Coverage: every comparable arm in the repository",
            "",
            "An arm that did not reach the snapshot minimum is listed here rather than "
            "omitted. A short sequence usually means the arm was measured once, for one "
            "preregistered question, and then never re-run.",
            "",
            "`Committed runs` counts every qualifying receipt in the arm; `snapshots` is what "
            "survives the one-per-config rule. Where the two differ, the extra runs are "
            "repetitions at an unchanged pipeline config, or arms that differ only by a knob "
            "the config hash does not cover — the two Variant-C context budgets are the case "
            "in this repository.",
            "",
            "| Arm | Golden set | Committed runs | Snapshots | Drawn |",
            "|---|---|---:|---:|---|",
        ]
    )
    for group in groups:
        lines.append(
            f"| {group.label} | `{group.golden_set_hash[:8]}` | "
            f"{len(group.all_snapshots)} | {len(group.snapshots)} | "
            f"{'yes' if group.is_sequence else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Runs excluded from every sequence",
            "",
            "| Run id | Reason |",
            "|---|---|",
        ]
    )
    if exclusions:
        for run_id, _, reason in sorted(exclusions):
            lines.append(f"| `{run_id}` | {reason} |")
    else:
        lines.append("| — | no committed generation run was excluded |")

    lines.extend(
        [
            "",
            "## Taxonomy",
            "",
            "| Code | What it records |",
            "|---|---|",
        ]
    )
    for code, meaning in TAXONOMY:
        lines.append(f"| `{code}` | {meaning} |")
    lines.extend(
        [
            "",
            "`RANK_MISS` is raised by the retrieval evals and never appears beside the "
            "generation codes: those receipts score a different population (the rows carrying "
            "expected documents) and are reported in `reports/variant_matrix.md` instead.",
        ]
    )

    receipt = {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "config_hash": _config_hash(),
        "product_prompt_sha256": PROMPT_SHA256,
        "shipped_decoding": {
            "temperature": cfg.generation.temperature,
            "top_p": cfg.generation.top_p,
        },
        "minimum_sequence": MIN_SEQUENCE,
        "sequences": receipt_sequences,
        "coverage": [
            {
                "variant": group.variant,
                "model": group.model,
                "rows": group.rows,
                "golden_set_hash": group.golden_set_hash,
                "committed_runs": len(group.all_snapshots),
                "snapshots": len(group.snapshots),
                "drawn": group.is_sequence,
            }
            for group in groups
        ],
        "exclusions": [
            {"run_id": run_id, "path": path, "reason": reason}
            for run_id, path, reason in sorted(exclusions)
        ],
    }
    return "\n".join(lines) + "\n", receipt


def run_failure_pareto(args: Namespace) -> int:
    report_path = Path(args.report)
    receipt_path = Path(args.receipt)
    text, receipt = build_report(chart_dir=Path(args.chart_dir))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"failure pareto: {report_path}")
    print(f"receipt: {receipt_path}")
    for key, entry in receipt["sequences"].items():
        print(f"  sequence {key}: {entry['chart']}")
    return 0


__all__ = [
    "MIN_SEQUENCE",
    "TAXONOMY",
    "Group",
    "Snapshot",
    "build_report",
    "collect_groups",
    "run_failure_pareto",
    "sequence_verdict",
    "write_chart",
]
