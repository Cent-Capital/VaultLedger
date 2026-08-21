"""Phase 12 routing accuracy and four-policy latency–quality frontier."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from uuid import uuid4

from vaultledger.config import Config, load_config
from vaultledger.evals.golden import golden_hash, load_golden_set
from vaultledger.provenance import config_hash, git_sha
from vaultledger.route import PolicyRouter, escalation_trigger
from vaultledger.schemas import Answer, QAExample, RunManifest

POLICIES = ("all_t0", "all_t1", "category_static", "policy_router")


def build_policy_router(cfg: Config) -> PolicyRouter:
    return PolicyRouter(
        models={"T0": cfg.models.T0.id, "T1": cfg.models.T1.id},
        t0_categories=set(cfg.router.t0_categories),
        rerank_tau=cfg.thresholds.rerank_tau,
        projected_cost_usd={
            "T0": cfg.router.projected_cost_usd["T0"],
            "T1": cfg.router.projected_cost_usd["T1"],
        },
    )


def _rows_by_id(rows: list[dict]) -> dict[str, dict]:
    indexed = {str(row["example_id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("answer receipt contains duplicate example ids")
    return indexed


def _rank(row: dict) -> tuple[int, float]:
    if row.get("error"):
        return (0, 0.0)
    answer = Answer.model_validate(row["answer"])
    downgraded = any(
        event.action == "downgrade_to_abstain" for event in answer.guardrail_events
    )
    return (int(not answer.abstained and not downgraded), answer.confidence)


def _latency_ms(row: dict) -> float:
    if row.get("gateway"):
        return float(row["gateway"]["latency_ms"])
    return float(row.get("wall_latency_ms", 0.0))


def _selected_policy_row(
    *,
    policy: str,
    example: QAExample,
    t0: dict,
    t1: dict,
    router: PolicyRouter,
    remaining_budget_usd: float,
) -> tuple[dict, list[dict], str | None]:
    if policy == "all_t0":
        return t0, [t0], None
    if policy == "all_t1":
        return t1, [t1], None

    decision = router.decide(
        category=example.category,
        remaining_budget_usd=remaining_budget_usd,
    )
    initial = t0 if decision.chosen_tier == "T0" else t1
    if policy == "category_static" or decision.chosen_tier == "T1":
        return initial, [initial], None
    if policy != "policy_router":
        raise ValueError(f"unknown frontier policy: {policy}")

    if initial.get("error"):
        trigger = "initial tier returned TOOL_ERR"
    else:
        answer = Answer.model_validate(initial["answer"])
        trigger = escalation_trigger(
            answer,
            category=example.category,
            rerank_tau=router.rerank_tau,
        )
    if trigger is None:
        return initial, [initial], None
    escalated = t1
    selected = max((initial, escalated), key=_rank)
    return selected, [initial, escalated], trigger


def evaluate_policies(
    examples: list[QAExample],
    t0_rows: list[dict],
    t1_rows: list[dict],
    *,
    router: PolicyRouter,
    remaining_budget_usd: float,
) -> tuple[dict[str, float], list[dict], list[dict]]:
    """Score routing labels and four policies over the same cached answers."""
    t0_by_id = _rows_by_id(t0_rows)
    t1_by_id = _rows_by_id(t1_rows)
    expected_ids = {example.id for example in examples}
    for tier, rows in (("T0", t0_by_id), ("T1", t1_by_id)):
        missing = sorted(expected_ids - rows.keys())
        if missing:
            raise ValueError(f"{tier} answer receipt is missing {len(missing)} examples")

    failures: list[dict] = []
    decisions: list[dict] = []
    correct_routes = 0
    for example in examples:
        decision = router.decide(
            category=example.category,
            remaining_budget_usd=remaining_budget_usd,
        )
        correct = decision.chosen_tier == example.expected_tier
        correct_routes += int(correct)
        decisions.append(
            {
                "example_id": example.id,
                "category": example.category,
                "expected_tier": example.expected_tier,
                "correct": correct,
                "decision": decision.model_dump(),
            }
        )
        if not correct:
            failures.append(
                {
                    "example_id": example.id,
                    "taxonomy_code": "ROUTE_ERR",
                    "note": (
                        f"expected {example.expected_tier}, chose {decision.chosen_tier}: "
                        f"{decision.reason}"
                    ),
                }
            )

    metrics: dict[str, float] = {
        "routing_accuracy": correct_routes / len(examples) if examples else 0.0,
        "routing_eval_n": float(len(examples)),
    }
    policy_rows: list[dict] = []
    for policy in POLICIES:
        selected_rows: list[dict] = []
        latencies: list[float] = []
        escalated_n = 0
        improved_n = 0
        for example in examples:
            t0 = t0_by_id[example.id]
            t1 = t1_by_id[example.id]
            selected, attempted, trigger = _selected_policy_row(
                policy=policy,
                example=example,
                t0=t0,
                t1=t1,
                router=router,
                remaining_budget_usd=remaining_budget_usd,
            )
            selected_rows.append(selected)
            latencies.append(sum(_latency_ms(row) for row in attempted))
            if trigger is not None:
                escalated_n += 1
                improved_n += int(
                    bool(selected.get("strict_match"))
                    and not bool(attempted[0].get("strict_match"))
                )
        n = len(examples)
        quality = (
            sum(bool(row.get("strict_match")) for row in selected_rows) / n if n else 0.0
        )
        citation = (
            sum(bool(row.get("citation_doc_hit")) for row in selected_rows) / n
            if n
            else 0.0
        )
        abstention = (
            sum(bool(row.get("abstention_correct")) for row in selected_rows) / n
            if n
            else 0.0
        )
        avg_latency = sum(latencies) / n if n else 0.0
        p50_latency = float(median(latencies)) if latencies else 0.0
        escalation_rate = escalated_n / n if n else 0.0
        efficacy = improved_n / escalated_n if escalated_n else 0.0
        metrics.update(
            {
                f"policy.{policy}.strict_match_rate": quality,
                f"policy.{policy}.citation_doc_hit_rate": citation,
                f"policy.{policy}.abstention_accuracy": abstention,
                f"policy.{policy}.avg_gateway_latency_ms": avg_latency,
                f"policy.{policy}.p50_gateway_latency_ms": p50_latency,
                f"policy.{policy}.escalation_rate": escalation_rate,
                f"policy.{policy}.escalation_efficacy": efficacy,
            }
        )
        policy_rows.append(
            {
                "policy": policy,
                "strict_match_rate": quality,
                "citation_doc_hit_rate": citation,
                "abstention_accuracy": abstention,
                "avg_gateway_latency_ms": avg_latency,
                "p50_gateway_latency_ms": p50_latency,
                "escalation_rate": escalation_rate,
                "escalation_efficacy": efficacy,
            }
        )
    return metrics, failures, [{"decisions": decisions, "policies": policy_rows}]


def _svg(manifest: RunManifest, output_path: Path) -> None:
    width, height = 820, 510
    left, right, top, bottom = 95, 55, 105, 80
    points = [
        (
            policy,
            manifest.metrics[f"policy.{policy}.avg_gateway_latency_ms"],
            manifest.metrics[f"policy.{policy}.strict_match_rate"],
        )
        for policy in POLICIES
    ]
    xs = [point[1] for point in points]
    x_min, x_max = 0.0, max(xs) * 1.12 or 1.0
    y_min, y_max = 0.0, 1.0

    def px(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * (width - left - right)

    def py(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * (height - top - bottom)

    colors = {
        "all_t0": "#64748b",
        "all_t1": "#334155",
        "category_static": "#d97706",
        "policy_router": "#7c3aed",
    }
    label_offsets = {
        "all_t0": (10, -12, "start"),
        "all_t1": (10, -12, "start"),
        "category_static": (10, 22, "start"),
        "policy_router": (-10, -12, "end"),
    }
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="95" y="32" font-family="sans-serif" font-size="20" '
        'font-weight="700" fill="#0f172a">Routing policies: latency vs strict match</text>',
        f'<text x="95" y="57" font-family="sans-serif" font-size="12" '
        f'fill="#475569">{int(manifest.metrics["routing_eval_n"])} golden queries · '
        'Variant B · cached local model answers · one measured run · timeouts retained</text>',
        '<text x="95" y="77" font-family="sans-serif" font-size="12" '
        'fill="#475569">Lower-left is faster; upper-left is better. Strict match is a '
        'literal-anchor lower bound, not a judge score.</text>',
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" '
        f'y2="{height-bottom}" stroke="#334155"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" '
        'stroke="#334155"/>',
        f'<text x="{width/2}" y="{height-20}" text-anchor="middle" '
        'font-family="sans-serif" font-size="14">Average gateway latency '
        '(ms, lower is better)</text>',
        f'<text x="22" y="{(top + height-bottom)/2}" text-anchor="middle" '
        'font-family="sans-serif" font-size="14" '
        f'transform="rotate(-90 22 {(top + height-bottom)/2})">'
        'Strict match rate (higher is better)</text>',
    ]
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = py(fraction)
        elements.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
                'stroke="#e2e8f0"/>',
                f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" '
                f'font-family="sans-serif" font-size="11" fill="#475569">'
                f'{fraction:.0%}</text>',
            ]
        )
    for policy, x_value, y_value in points:
        x, y = px(x_value), py(y_value)
        if policy == "all_t0":
            mark = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colors[policy]}"/>'
        elif policy == "all_t1":
            mark = (
                f'<rect x="{x-7:.1f}" y="{y-7:.1f}" width="14" height="14" '
                f'fill="{colors[policy]}"/>'
            )
        elif policy == "category_static":
            mark = (
                f'<polygon points="{x:.1f},{y-9:.1f} {x+9:.1f},{y:.1f} '
                f'{x:.1f},{y+9:.1f} {x-9:.1f},{y:.1f}" fill="{colors[policy]}"/>'
            )
        else:
            mark = (
                f'<polygon points="{x:.1f},{y-9:.1f} {x+9:.1f},{y+8:.1f} '
                f'{x-9:.1f},{y+8:.1f}" fill="{colors[policy]}"/>'
            )
        dx, dy, anchor = label_offsets[policy]
        elements.extend(
            [
                mark,
                f'<text x="{x+dx:.1f}" y="{y+dy:.1f}" font-family="sans-serif" '
                f'font-size="13" text-anchor="{anchor}" fill="#0f172a">'
                f'{policy}</text>',
            ]
        )
    elements.extend(
        [
            f'<text x="{left}" y="{height-bottom+22}" font-family="sans-serif" '
            f'font-size="11">{x_min:.0f}</text>',
            f'<text x="{width-right}" y="{height-bottom+22}" text-anchor="end" '
            f'font-family="sans-serif" font-size="11">{x_max:.0f}</text>',
            "</svg>",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(elements) + "\n")


def write_router_report(
    manifest_path: Path,
    details_path: Path,
    output_path: Path,
    chart_path: Path,
) -> None:
    manifest = RunManifest.model_validate_json(manifest_path.read_text())
    details = json.loads(details_path.read_text())
    source_runs = details["source_manifests"]
    lines = [
        "# Phase 12 routing frontier",
        "",
        f"Router manifest: `{manifest.run_id}`",
        f"Golden set hash: `{manifest.golden_set_hash}`",
        f"Source model cells: `{source_runs['T0']}`, `{source_runs['T1']}`",
        "",
        f"Routing accuracy: **{manifest.metrics['routing_accuracy']:.1%}** "
        f"over **{int(manifest.metrics['routing_eval_n'])}** labelled queries.",
        f"Source generation coverage: **T0 "
        f"{manifest.metrics['source.T0.generation_coverage']:.1%} / T1 "
        f"{manifest.metrics['source.T1.generation_coverage']:.1%}**. "
        "Failed source rows score as misses and retain their timeout wall latency.",
        "",
        "| Policy | Strict match | Citation hit | Abstention accuracy | "
        "Avg gateway latency | P50 gateway latency | Escalation rate | "
        "Escalation efficacy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for policy in POLICIES:
        prefix = f"policy.{policy}."
        lines.append(
            f"| `{policy}` | {manifest.metrics[prefix + 'strict_match_rate']:.1%} | "
            f"{manifest.metrics[prefix + 'citation_doc_hit_rate']:.1%} | "
            f"{manifest.metrics[prefix + 'abstention_accuracy']:.1%} | "
            f"{manifest.metrics[prefix + 'avg_gateway_latency_ms']:.0f} ms | "
            f"{manifest.metrics[prefix + 'p50_gateway_latency_ms']:.0f} ms | "
            f"{manifest.metrics[prefix + 'escalation_rate']:.1%} | "
            f"{manifest.metrics[prefix + 'escalation_efficacy']:.1%} |"
        )
    rel_chart = Path("paretos") / chart_path.name
    lines.extend(
        [
            "",
            f"![Latency–quality frontier]({rel_chart.as_posix()})",
            "",
            "Strict match is the conservative Phase-11 literal-anchor scorer, not an "
            "LLM-judge verdict. Dynamic-policy latency sums every attempted model call. "
            "The four policies reuse the exact same cached answers, so policy differences "
            "are routing effects rather than generation rerolls.",
            "",
            "Latency is noisy: Phase 11 observed about 10% p95 movement between identical "
            "runs. Treat close x-axis positions as unresolved until Phase 18 repeats cells "
            "and reports a spread. Local cost remains $0.0 (unpriced, not free).",
            "",
            "This report and its SVG are generated from the router RunManifest; per-query "
            "RoutingDecisions and source-cell ids live in the adjacent details receipt.",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    _svg(manifest, chart_path)


def _best_receipt(out_dir: Path, model_fragment: str) -> Path:
    candidates = list(out_dir.glob(f"phase11_*{model_fragment}*_answers.json"))
    if not candidates:
        raise FileNotFoundError(f"no matrix answer receipt found for {model_fragment}")

    def receipt_key(path: Path) -> tuple[int, str, str]:
        manifest_path, manifest = _source_manifest(path)
        return (len(json.loads(path.read_text())), manifest.timestamp, manifest_path.name)

    return max(candidates, key=receipt_key)


def _source_manifest(receipt: Path) -> tuple[Path, RunManifest]:
    suffix = "_answers.json"
    if not receipt.name.endswith(suffix):
        raise ValueError(f"not a matrix answer receipt: {receipt}")
    manifest_path = receipt.with_name(receipt.name[: -len(suffix)] + ".json")
    if not manifest_path.exists():
        raise FileNotFoundError(f"source manifest missing for {receipt}")
    return manifest_path, RunManifest.model_validate_json(manifest_path.read_text())


def run_router_eval(args: Namespace) -> int:
    cfg = load_config()
    golden = load_golden_set(args.golden)
    examples = golden.examples
    out_dir = Path(args.out_dir)
    t0_receipt = Path(args.t0_answers) if args.t0_answers else _best_receipt(out_dir, "4b")
    t1_receipt = Path(args.t1_answers) if args.t1_answers else _best_receipt(out_dir, "8b")
    t0_rows = json.loads(t0_receipt.read_text())
    t1_rows = json.loads(t1_receipt.read_text())
    if not args.allow_partial and (len(t0_rows) != len(examples) or len(t1_rows) != len(examples)):
        raise ValueError(
            "router frontier requires full-golden T0/T1 answer receipts; "
            "run the two-model matrix with `--limit 0` first"
        )
    if args.allow_partial:
        common_ids = {row["example_id"] for row in t0_rows} & {
            row["example_id"] for row in t1_rows
        }
        examples = [example for example in examples if example.id in common_ids]

    t0_manifest_path, t0_manifest = _source_manifest(t0_receipt)
    t1_manifest_path, t1_manifest = _source_manifest(t1_receipt)
    expected_hash = golden_hash(args.golden)
    if {t0_manifest.golden_set_hash, t1_manifest.golden_set_hash} != {expected_hash}:
        raise ValueError("source matrix manifests do not match the current golden-set hash")

    router = build_policy_router(cfg)
    metrics, failures, payload = evaluate_policies(
        examples,
        t0_rows,
        t1_rows,
        router=router,
        remaining_budget_usd=cfg.budgets.session_usd,
    )
    metrics.update(
        {
            "source.T0.generation_coverage": t0_manifest.metrics[
                "generation_eval_coverage"
            ],
            "source.T1.generation_coverage": t1_manifest.metrics[
                "generation_eval_coverage"
            ],
            "source.T0.tool_error_rate": (
                sum(bool(row.get("error")) for row in t0_rows) / len(t0_rows)
                if t0_rows
                else 0.0
            ),
            "source.T1.tool_error_rate": (
                sum(bool(row.get("error")) for row in t1_rows) / len(t1_rows)
                if t1_rows
                else 0.0
            ),
        }
    )
    manifest = RunManifest(
        run_id=f"phase12_router_{uuid4().hex[:12]}",
        timestamp=datetime.now(UTC).isoformat(),
        git_sha=git_sha(),
        config_hash=config_hash(),
        golden_set_hash=expected_hash,
        seed=cfg.seed,
        variant="B_hybrid",
        model=f"policy_router_v2[{cfg.models.T0.id},{cfg.models.T1.id}]",
        metrics=metrics,
        total_cost_usd=0.0,
        failures=failures,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"{manifest.run_id}.json"
    details_path = out_dir / f"{manifest.run_id}_details.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    details = payload[0]
    details["source_manifests"] = {
        "T0": t0_manifest.run_id,
        "T1": t1_manifest.run_id,
    }
    details["source_paths"] = {
        "T0": str(t0_manifest_path),
        "T1": str(t1_manifest_path),
    }
    details["source_tool_errors"] = {
        "T0": [row["example_id"] for row in t0_rows if row.get("error")],
        "T1": [row["example_id"] for row in t1_rows if row.get("error")],
    }
    details_path.write_text(json.dumps(details, indent=2) + "\n")
    latest_path = out_dir / "phase12_router_latest.json"
    latest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    report_path = Path(args.report)
    chart_path = Path(args.chart)
    write_router_report(manifest_path, details_path, report_path, chart_path)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "details": str(details_path),
                "report": str(report_path),
                "chart": str(chart_path),
                "metrics": metrics,
            },
            indent=2,
        )
    )
    return int(metrics["routing_accuracy"] < 0.9)


__all__ = [
    "POLICIES",
    "build_policy_router",
    "evaluate_policies",
    "run_router_eval",
    "write_router_report",
]
