"""Phase 11 multi-model matrix runner and generated report."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

from vaultledger.config import CONFIG_PATH, Config, load_config
from vaultledger.evals.golden import golden_hash, load_golden_set
from vaultledger.gateway import GatewayTotals, LiteLLMGenerator
from vaultledger.generate import answer_question_reliable
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.retrieve import CrossEncoderReranker, HybridRetriever, NaiveDenseRetriever
from vaultledger.schemas import Answer, QAExample, RoutingDecision, RunManifest

_AMOUNT = re.compile(r"\$\s*\d[\d,]*(?:\.\d{2})?")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+){2,}\b")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _config_hash() -> str:
    return hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()


def _canonical(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.]+", " ", text.casefold()).split())


def strict_answer_match(example: QAExample, answer: Answer) -> tuple[bool, str]:
    """Conservative deterministic score used until Phase 17's judged bake-off.

    Unanswerable examples are scored on abstention.  For answerable examples,
    every literal amount/date/identifier in the reference must occur in the
    candidate; references without those anchors require a full normalized
    substring match.  This intentionally under-credits valid paraphrases and is
    never presented as an LLM-judge verdict.
    """
    if example.category == "unanswerable":
        return answer.abstained, "rightly abstained" if answer.abstained else "answered"
    if answer.abstained:
        return False, "abstained on an answerable example"

    expected = example.expected_answer
    anchors = _AMOUNT.findall(expected) + _DATE.findall(expected) + _IDENTIFIER.findall(expected)
    if anchors:
        candidate = _canonical(answer.answer_text)
        missing = [anchor for anchor in anchors if _canonical(anchor) not in candidate]
        if missing:
            return False, f"missing literal anchors: {', '.join(missing)}"
        return True, f"matched {len(anchors)} literal anchor(s)"
    matched = _canonical(expected) in _canonical(answer.answer_text)
    return matched, "normalized reference substring matched" if matched else (
        "normalized reference substring absent"
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _required_inputs(cfg: Config, variants: list[str]) -> None:
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    required = [index_dir / "chunks.jsonl", index_dir / "chroma", index_dir / "records.db"]
    if "B_hybrid" in variants:
        required.append(index_dir / "bm25.json")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "missing index artifacts; run `make data && make ingest` first: "
            + ", ".join(missing)
        )


def _retrievers(cfg: Config, variants: list[str]) -> dict[str, object]:
    unsupported = sorted(set(variants) - {"A_naive", "B_hybrid"})
    if unsupported:
        raise ValueError(
            f"variants not built yet: {', '.join(unsupported)}; Phase 11 supports A_naive/B_hybrid"
        )
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
    if not embedder.is_available():
        raise RuntimeError(
            f"embedding model {cfg.embedding.model!r} is unavailable at "
            f"{cfg.embedding.ollama_url}"
        )
    built: dict[str, object] = {}
    if "A_naive" in variants:
        built["A_naive"] = NaiveDenseRetriever(index_dir, embedder)
    if "B_hybrid" in variants:
        reranker = (
            CrossEncoderReranker(cfg.reranker.model, cfg.reranker.batch_size)
            if cfg.reranker.enabled
            else None
        )
        built["B_hybrid"] = HybridRetriever(
            index_dir,
            embedder,
            candidate_k=cfg.retrieval.candidate_k,
            rank_constant=cfg.retrieval.rrf_constant,
            reranker=reranker,
        )
    return built


def _cell_metrics(
    examples: list[QAExample],
    rows: list[dict],
    totals: GatewayTotals,
) -> dict[str, float]:
    completed = [row for row in rows if not row.get("error")]
    n = len(examples)
    latencies = [float(row["gateway"]["latency_ms"]) for row in completed]
    calls = [
        call
        for row in completed
        for call in row["gateway"].get("token_sources", [])
    ]
    pricing_statuses = [
        status
        for row in completed
        for status in row["gateway"].get("pricing_statuses", [])
    ]
    return {
        "matrix_examples": float(n),
        "generation_eval_coverage": len(completed) / n if n else 0.0,
        "strict_answer_match_rate": (
            sum(bool(row["strict_match"]) for row in completed) / n if n else 0.0
        ),
        "citation_doc_hit_rate": (
            sum(bool(row["citation_doc_hit"]) for row in completed) / n if n else 0.0
        ),
        "abstention_accuracy": (
            sum(bool(row["abstention_correct"]) for row in completed) / n if n else 0.0
        ),
        "median_gateway_latency_ms": round(float(median(latencies)), 3) if latencies else 0.0,
        "p95_gateway_latency_ms": round(_percentile(latencies, 0.95), 3),
        "gateway_calls": float(totals.calls),
        "input_tokens": float(totals.input_tokens),
        "output_tokens": float(totals.output_tokens),
        "provider_token_usage_rate": (
            sum(source == "provider_usage" for source in calls) / len(calls) if calls else 0.0
        ),
        "model_unpriced": float(
            bool(pricing_statuses)
            and all(status == "unpriced" for status in pricing_statuses)
        ),
    }


def _totals_from_rows(rows: list[dict]) -> GatewayTotals:
    gateways = [row["gateway"] for row in rows if not row.get("error")]
    return GatewayTotals(
        calls=sum(int(gateway["calls"]) for gateway in gateways),
        latency_ms=round(sum(float(gateway["latency_ms"]) for gateway in gateways), 3),
        input_tokens=sum(int(gateway["input_tokens"]) for gateway in gateways),
        output_tokens=sum(int(gateway["output_tokens"]) for gateway in gateways),
        cost_usd=round(sum(float(gateway["cost_usd"]) for gateway in gateways), 10),
    )


def _run_cell(
    *,
    cfg: Config,
    model: str,
    variant: str,
    retriever: object,
    examples: list[QAExample],
    golden_set_hash: str,
    out_dir: Path,
) -> tuple[Path, Path]:
    generator = LiteLLMGenerator(model, base_url=cfg.embedding.ollama_url)
    if not generator.is_available():
        raise RuntimeError(f"matrix model {model!r} is unavailable in Ollama")

    slug = re.sub(r"[^a-z0-9]+", "_", model.casefold()).strip("_")
    checkpoint_path = out_dir / f".matrix_checkpoint_{slug}_{variant.casefold()}.json"
    checkpoint_key = {
        "model": model,
        "variant": variant,
        "config_hash": _config_hash(),
        "golden_set_hash": golden_set_hash,
        "example_ids": [example.id for example in examples],
    }
    rows: list[dict] = []
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if all(checkpoint.get(key) == value for key, value in checkpoint_key.items()):
            rows = list(checkpoint.get("rows", []))
            print(
                f"matrix resume: {model} × {variant} at {len(rows)}/{len(examples)}",
                flush=True,
            )
    completed_ids = {str(row["example_id"]) for row in rows}
    for example in examples:
        if example.id in completed_ids:
            continue
        before = generator.snapshot()
        call_start = len(generator.calls)
        started = perf_counter()
        tier = "T0" if model == cfg.models.T0.id else "T1"
        routing = RoutingDecision(
            query_id=f"q_{uuid4().hex[:12]}",
            allowed_tiers=[tier],
            chosen_tier=tier,
            chosen_model=model,
            reason="Phase 11 local matrix cell: model and tier pinned by the manifest",
            est_cost_usd=0.0,
            actual_cost_usd=0.0,
        )
        try:
            answer = answer_question_reliable(
                example.question,
                retriever,  # type: ignore[arg-type]
                generator,
                model_id=model,
                k=cfg.retrieval.answer_top_n,
                max_retries=cfg.loops.repair_max,
                min_snippet_chars=cfg.generation.min_snippet_chars,
                routing=routing,
                reorder_context=cfg.generation.litm_reorder,
            )
        except Exception as exc:
            failure = {
                "example_id": example.id,
                "taxonomy_code": "TOOL_ERR",
                "note": f"matrix cell failed to produce an Answer: {exc}",
            }
            rows.append(
                {
                    "example_id": example.id,
                    "error": str(exc),
                    "wall_latency_ms": round((perf_counter() - started) * 1000, 3),
                    "failure": failure,
                }
            )
            checkpoint_path.write_text(json.dumps({**checkpoint_key, "rows": rows}, indent=2))
            print(
                f"matrix checkpoint: {model} × {variant} {len(rows)}/{len(examples)} "
                f"(TOOL_ERR)",
                flush=True,
            )
            continue

        usage = generator.snapshot().delta(before)
        gateway_calls = generator.calls[call_start:]
        matched, reason = strict_answer_match(example, answer)
        expected_docs = set(example.expected_doc_ids)
        cited_docs = {citation.doc_id for citation in answer.citations}
        citation_hit = not expected_docs or bool(expected_docs & cited_docs)
        abstention_correct = answer.abstained == (example.category == "unanswerable")
        failure = None
        if not abstention_correct:
            failure = {
                "example_id": example.id,
                "taxonomy_code": "ABSTAIN_FP" if answer.abstained else "ABSTAIN_FN",
                "note": reason,
            }
        elif not matched:
            failure = {
                "example_id": example.id,
                "taxonomy_code": (
                    "NUM_MISMATCH"
                    if _AMOUNT.search(example.expected_answer)
                    else "GEN_HALLUC"
                ),
                "note": f"strict deterministic scorer: {reason}; judge review deferred",
            }
        elif not citation_hit:
            failure = {
                "example_id": example.id,
                "taxonomy_code": "CITE_FAIL",
                "note": "no cited document matched the golden expected documents",
            }
        rows.append(
            {
                "example_id": example.id,
                "category": example.category,
                "expected_answer": example.expected_answer,
                "strict_match": matched,
                "score_reason": reason,
                "citation_doc_hit": citation_hit,
                "abstention_correct": abstention_correct,
                "wall_latency_ms": round((perf_counter() - started) * 1000, 3),
                "gateway": {
                    "calls": usage.calls,
                    "latency_ms": usage.latency_ms,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cost_usd": usage.cost_usd,
                    "token_sources": [call.token_source for call in gateway_calls],
                    "pricing_statuses": [call.pricing_status for call in gateway_calls],
                },
                "answer": answer.model_dump(),
                "failure": failure,
            }
        )
        checkpoint_path.write_text(json.dumps({**checkpoint_key, "rows": rows}, indent=2))
        print(
            f"matrix checkpoint: {model} × {variant} {len(rows)}/{len(examples)}",
            flush=True,
        )

    order = {example.id: index for index, example in enumerate(examples)}
    rows.sort(key=lambda row: order[str(row["example_id"])])
    totals = _totals_from_rows(rows)
    metrics = _cell_metrics(examples, rows, totals)
    failures = [row["failure"] for row in rows if row.get("failure")]
    manifest = RunManifest(
        run_id=f"phase11_{slug}_{variant.casefold()}_{uuid4().hex[:12]}",
        timestamp=datetime.now(UTC).isoformat(),
        git_sha=_git_sha(),
        config_hash=_config_hash(),
        golden_set_hash=golden_set_hash,
        seed=cfg.seed,
        variant=variant,  # type: ignore[arg-type]
        model=model,
        metrics=metrics,
        total_cost_usd=totals.cost_usd,
        failures=failures,
    )
    manifest_path = out_dir / f"{manifest.run_id}.json"
    answers_path = out_dir / f"{manifest.run_id}_answers.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    answers_path.write_text(json.dumps(rows, indent=2) + "\n")
    checkpoint_path.unlink(missing_ok=True)
    return manifest_path, answers_path


def write_matrix_report(manifest_paths: list[Path], output_path: Path) -> None:
    manifests = [RunManifest.model_validate_json(path.read_text()) for path in manifest_paths]
    if not manifests:
        raise ValueError("cannot generate a model matrix without manifests")
    hashes = {manifest.golden_set_hash for manifest in manifests}
    if len(hashes) != 1:
        raise ValueError("matrix manifests use different golden sets")
    total_cost = sum(manifest.total_cost_usd for manifest in manifests)
    model_count = len({manifest.model for manifest in manifests})
    lines = [
        "# Model matrix",
        "",
        "Phase 11 gateway/matrix machinery proof. The full six-model bake-off is Phase 17.",
        "",
        f"Golden set hash: `{manifests[0].golden_set_hash}`",
        f"Cells: **{len(manifests)}** across **{model_count} model(s)**",
        f"Total measured API spend: **${total_cost:.6f}** (local models are unpriced, not free)",
        "",
        "| Model | Variant | N | Strict match | Citation hit | Abstention accuracy | "
        "Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for manifest in sorted(manifests, key=lambda item: (item.model, item.variant)):
        metric = manifest.metrics
        lines.append(
            "| "
            f"`{manifest.model}` | `{manifest.variant}` | {int(metric['matrix_examples'])} | "
            f"{metric['strict_answer_match_rate']:.1%} | "
            f"{metric['citation_doc_hit_rate']:.1%} | "
            f"{metric['abstention_accuracy']:.1%} | "
            f"{metric['median_gateway_latency_ms']:.0f} ms | "
            f"{metric['p95_gateway_latency_ms']:.0f} ms | "
            f"{int(metric['input_tokens'])} / {int(metric['output_tokens'])} | "
            f"${manifest.total_cost_usd:.6f} | `{manifest.run_id}` |"
        )
    lines.extend(
        [
            "",
            "## Reading the result",
            "",
            "`Strict match` is a deterministic lower-bound scorer: answerable rows must repeat "
            "the reference's literal amounts, dates, and identifiers; other rows require a "
            "normalized reference substring. It under-credits valid paraphrases and is not an "
            "LLM-judge verdict. Per-example reasons and complete answers live beside each "
            "manifest in its `_answers.json` receipt.",
            "",
            "Gateway latency covers all completion calls, including structured-output repairs. "
            "Retrieval and reranking time is excluded. Token counts come from provider usage when "
            "available. Every displayed value is loaded from the RunManifests above; this file is "
            "generated, never hand-edited.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines))


def run_matrix(args: Namespace) -> int:
    cfg = load_config()
    models = args.models or [model.id for model in cfg.models.matrix]
    variants = args.variants or cfg.matrix.variants
    limit = cfg.matrix.smoke_limit if args.limit is None else args.limit
    if len(set(models)) != len(models):
        raise ValueError("matrix model ids must be unique")
    if len(set(variants)) != len(variants):
        raise ValueError("matrix variants must be unique")
    _required_inputs(cfg, variants)
    golden = load_golden_set(args.golden)
    examples = golden.examples[:limit] if limit else golden.examples
    retrievers = _retrievers(cfg, variants)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    receipts: list[str] = []
    for model in models:
        for variant in variants:
            manifest_path, answers_path = _run_cell(
                cfg=cfg,
                model=model,
                variant=variant,
                retriever=retrievers[variant],
                examples=examples,
                golden_set_hash=golden_hash(args.golden),
                out_dir=out_dir,
            )
            paths.append(manifest_path)
            receipts.append(str(answers_path))

    total_cost = sum(
        RunManifest.model_validate_json(path.read_text()).total_cost_usd for path in paths
    )
    if total_cost > cfg.budgets.session_usd:
        raise RuntimeError(
            f"matrix cost ${total_cost:.6f} exceeded session budget ${cfg.budgets.session_usd:.2f}"
        )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_matrix_report(paths, report_path)
    print(
        json.dumps(
            {
                "report": str(report_path),
                "manifests": [str(path) for path in paths],
                "answer_receipts": receipts,
                "models": models,
                "variants": variants,
                "examples_per_cell": len(examples),
                "total_cost_usd": total_cost,
            },
            indent=2,
        )
    )
    return 0


__all__ = ["run_matrix", "strict_answer_match", "write_matrix_report"]
