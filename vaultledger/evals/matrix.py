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
from vaultledger.guardrails import GuardrailToggles
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.retrieve import CrossEncoderReranker, HybridRetriever, NaiveDenseRetriever
from vaultledger.schemas import Answer, QAExample, RoutingDecision, RunManifest

_AMOUNT = re.compile(r"\$\s*\d[\d,]*(?:\.\d{2})?")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+){2,}\b")

# The two sides of numeric exact-match are read with deliberately different
# patterns, and the asymmetry is the point.
#
# Reference side (strict): a quantity is a currency figure or a bare two-decimal
# number. Bare integers are excluded — this corpus is full of 1099s, four-digit
# years, and invoice counts, and treating "1099" as a figure the answer must
# reproduce would put rows in scope that carry no measurable number at all.
#
# Candidate side (permissive): any number, with or without a currency marker,
# commas, or cents. Scoring "$8,500" as a miss against a reference of "$8,500.00"
# would be a formatting judgement, and `strict_answer_match` already makes that
# judgement — a second metric that repeated it would earn its place nowhere.
_REFERENCE_QUANTITY = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?|(?<![\w$.])\d[\d,]*\.\d{2}(?![\d])")
_CANDIDATE_QUANTITY = re.compile(r"(?<![\w.])\$?\s*\d[\d,]*(?:\.\d+)?(?![\d])")


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


def _quantities(pattern: re.Pattern[str], text: str) -> list[float]:
    return [float(match.lstrip("$").replace(",", "").strip()) for match in pattern.findall(text)]


def numeric_reference_quantities(example: QAExample) -> list[float]:
    """The numeric quantities a correct answer has to reproduce.

    An empty list means the example is **out of scope** for numeric exact-match —
    not that it failed.  Scope is a property of the reference answer alone, so an
    example that never produced an `Answer` can still be placed in or out of the
    denominator.  `unanswerable` rows are always out of scope; whether the model
    should have declined to answer is what `abstention_accuracy` measures.
    """
    if example.category == "unanswerable":
        return []
    return _quantities(_REFERENCE_QUANTITY, example.expected_answer)


def numeric_exact_match(
    example: QAExample,
    answer: Answer,
    *,
    epsilon: float,
) -> tuple[bool | None, str]:
    """Numeric exact-match: every quantity in the reference, present in the answer.

    Distinct from `strict_answer_match`, which compares literal *strings* after
    normalization and so scores "$1,234.50" against "1234.5" as a miss.  Here both
    sides are parsed to floats and compared within `epsilon`, which is what SPEC's
    "numeric exact-match" names.

    Returns `None` when the example is out of scope (see
    `numeric_reference_quantities`), so callers can hold out-of-scope rows out of
    the denominator instead of scoring them as failures.

    **This is a presence test, not a correctness test.** It asks whether each
    reference figure appears somewhere in the answer; it cannot tell whether the
    answer *used* the figure correctly, and because the candidate side reads any
    number, a verbose answer reciting many figures can satisfy it by coincidence.
    That bias runs toward crediting the model, the opposite direction from
    `strict_answer_match`'s bias — so the two are not interchangeable and neither
    is an LLM-judge verdict.
    """
    expected = numeric_reference_quantities(example)
    if not expected:
        return None, "no numeric quantity in the reference; out of scope"
    if answer.abstained:
        return False, "abstained on a numeric example"
    candidate = _quantities(_CANDIDATE_QUANTITY, answer.answer_text)
    missing = [
        value
        for value in expected
        if not any(abs(value - found) <= epsilon for found in candidate)
    ]
    if missing:
        return False, "missing quantities: " + ", ".join(f"{value:,.2f}" for value in missing)
    return True, f"matched {len(expected)} quantity/quantities within {epsilon}"


def score_answer(example: QAExample, answer: Answer, *, numeric_epsilon: float) -> dict:
    """Every per-row score in one place.

    The live matrix and the offline `rescore` path both call this, so a baseline
    recomputed from a committed receipt and a fresh variant-D cell are comparable
    by construction rather than by a number someone pasted between them.
    """
    matched, reason = strict_answer_match(example, answer)
    numeric, numeric_reason = numeric_exact_match(example, answer, epsilon=numeric_epsilon)
    expected_docs = set(example.expected_doc_ids)
    cited_docs = {citation.doc_id for citation in answer.citations}
    return {
        "category": example.category,
        "strict_match": matched,
        "score_reason": reason,
        "numeric_exact_match": numeric,
        "numeric_score_reason": numeric_reason,
        "citation_doc_hit": not expected_docs or bool(expected_docs & cited_docs),
        "abstention_correct": answer.abstained == (example.category == "unanswerable"),
    }


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


#: Row-level flags that get a rate, aggregate and per category.
_RATES = (
    ("strict_answer_match_rate", "strict_match"),
    ("citation_doc_hit_rate", "citation_doc_hit"),
    ("abstention_accuracy", "abstention_correct"),
)


def _rate(rows: list[dict], field: str, denominator: int) -> float:
    return sum(bool(row.get(field)) for row in rows) / denominator if denominator else 0.0


def category_metrics(examples: list[QAExample], rows: list[dict]) -> dict[str, float]:
    """Category-scoped rates, keyed `<metric>__<category>`.

    Denominators come from `examples`, never from `rows`: a row that failed to
    produce an `Answer` counts as a miss inside its category rather than quietly
    shrinking the population.  That is the same convention the aggregate rates
    already use, and keeping it identical is what makes the two comparable.

    Emitting these is what makes a per-category regression visible without a
    one-off script.  Aggregate-only metrics are what let the router's
    category→tier map stay backwards on 44 of 80 rows without anything failing.
    """
    scored = {str(row["example_id"]): row for row in rows}
    metrics: dict[str, float] = {}
    for category in sorted({example.category for example in examples}):
        members = [example for example in examples if example.category == category]
        completed = [
            row
            for row in (scored.get(example.id) for example in members)
            if row is not None and not row.get("error")
        ]
        metrics[f"matrix_examples__{category}"] = float(len(members))
        for key, field in _RATES:
            metrics[f"{key}__{category}"] = _rate(completed, field, len(members))

        # Numeric exact-match carries its own denominator: rows whose reference
        # has no quantity are out of scope, not failures. Scope is read off the
        # example so an errored row still lands in the right population.
        in_scope = {
            example.id for example in members if numeric_reference_quantities(example)
        }
        metrics[f"numeric_exact_match_examples__{category}"] = float(len(in_scope))
        # The rate key is omitted, not set to 0.0, when nothing is in scope.
        # `metrics` is dict[str, float] and cannot hold "not applicable", and a
        # stored 0.0 is indistinguishable from a measured total failure — exactly
        # the kind of drift this repo has already had to withdraw twice.
        if in_scope:
            metrics[f"numeric_exact_match_rate__{category}"] = _rate(
                [row for row in completed if str(row["example_id"]) in in_scope],
                "numeric_exact_match",
                len(in_scope),
            )
    return metrics


def _cell_metrics(
    examples: list[QAExample],
    rows: list[dict],
    totals: GatewayTotals,
) -> dict[str, float]:
    completed = [row for row in rows if not row.get("error")]
    n = len(examples)
    numeric_scope = {
        example.id for example in examples if numeric_reference_quantities(example)
    }
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
        **{key: _rate(completed, field, n) for key, field in _RATES},
        "numeric_exact_match_examples": float(len(numeric_scope)),
        **(
            {
                "numeric_exact_match_rate": _rate(
                    [row for row in completed if str(row["example_id"]) in numeric_scope],
                    "numeric_exact_match",
                    len(numeric_scope),
                )
            }
            if numeric_scope
            else {}
        ),
        **category_metrics(examples, rows),
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
    guardrail_toggles: GuardrailToggles | None = None,
    records_db: Path | None = None,
) -> tuple[Path, Path]:
    generator = LiteLLMGenerator(model, base_url=cfg.embedding.ollama_url)
    if not generator.is_available():
        raise RuntimeError(f"matrix model {model!r} is unavailable in Ollama")

    slug = re.sub(r"[^a-z0-9]+", "_", model.casefold()).strip("_")
    arm = "on" if guardrail_toggles is not None else "off"
    checkpoint_path = out_dir / f".matrix_checkpoint_{slug}_{variant.casefold()}_{arm}.json"
    checkpoint_key = {
        "model": model,
        "variant": variant,
        "config_hash": _config_hash(),
        "golden_set_hash": golden_set_hash,
        # The guard arm is part of the key: an off-arm checkpoint must never be
        # resumed into an on-arm run, or the cell would mix two pipelines.
        "guardrails": arm,
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
                guardrail_toggles=guardrail_toggles,
                records_db=records_db,
                numeric_epsilon=cfg.thresholds.numeric_epsilon,
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
                    # Category travels even on the failure path, so a per-category
                    # receipt can be read without joining back to the golden set.
                    "category": example.category,
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
        scores = score_answer(example, answer, numeric_epsilon=cfg.thresholds.numeric_epsilon)
        matched = scores["strict_match"]
        reason = scores["score_reason"]
        citation_hit = scores["citation_doc_hit"]
        abstention_correct = scores["abstention_correct"]
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
                "expected_answer": example.expected_answer,
                **scores,
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
    # Self-describing arm: a manifest must say which guard stack produced it, or
    # on-arm and off-arm cells become silently incomparable in the matrix.
    metrics["guardrails_enabled"] = 1.0 if guardrail_toggles is not None else 0.0
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
        "| Model | Variant | N | Strict match | Numeric exact match | Citation hit | "
        "Abstention accuracy | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for manifest in sorted(manifests, key=lambda item: (item.model, item.variant)):
        metric = manifest.metrics
        # Manifests written before this metric existed are shown as "—" rather
        # than back-filled with a zero that would read as a measured failure.
        numeric_n = int(metric.get("numeric_exact_match_examples", 0.0))
        numeric = (
            f"{metric['numeric_exact_match_rate']:.1%} (n={numeric_n})" if numeric_n else "—"
        )
        lines.append(
            "| "
            f"`{manifest.model}` | `{manifest.variant}` | {int(metric['matrix_examples'])} | "
            f"{metric['strict_answer_match_rate']:.1%} | "
            f"{numeric} | "
            f"{metric['citation_doc_hit_rate']:.1%} | "
            f"{metric['abstention_accuracy']:.1%} | "
            f"{metric['median_gateway_latency_ms']:.0f} ms | "
            f"{metric['p95_gateway_latency_ms']:.0f} ms | "
            f"{int(metric['input_tokens'])} / {int(metric['output_tokens'])} | "
            f"${manifest.total_cost_usd:.6f} | `{manifest.run_id}` |"
        )
    categories = sorted(
        {
            key.split("__", 1)[1]
            for manifest in manifests
            for key in manifest.metrics
            if key.startswith("matrix_examples__")
        }
    )
    if categories:
        lines.extend(
            [
                "",
                "## By category",
                "",
                "Phase 14's acceptance criterion is stated per category, so the aggregate row "
                "above cannot verify it. `Numeric` is scored only over rows whose reference "
                "carries a numeric quantity; its `n` differs from the category `n` for that "
                "reason, and a blank cell means no row in that category is in scope.",
                "",
                "| Model | Variant | Category | N | Strict match | Numeric exact match | "
                "Citation hit | Abstention accuracy |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for manifest in sorted(manifests, key=lambda item: (item.model, item.variant)):
            metric = manifest.metrics
            for category in categories:
                count = metric.get(f"matrix_examples__{category}")
                if count is None:
                    continue
                numeric_n = int(metric.get(f"numeric_exact_match_examples__{category}", 0.0))
                numeric = (
                    f"{metric[f'numeric_exact_match_rate__{category}']:.1%} (n={numeric_n})"
                    if numeric_n
                    else "—"
                )
                lines.append(
                    "| "
                    f"`{manifest.model}` | `{manifest.variant}` | `{category}` | "
                    f"{int(count)} | "
                    f"{metric[f'strict_answer_match_rate__{category}']:.1%} | "
                    f"{numeric} | "
                    f"{metric[f'citation_doc_hit_rate__{category}']:.1%} | "
                    f"{metric[f'abstention_accuracy__{category}']:.1%} |"
                )
    lines.extend(
        [
            "",
            "## Reading the result",
            "",
            "`Numeric exact match` parses every quantity out of the reference answer and "
            "requires each one to appear in the candidate as a number equal within "
            "`thresholds.numeric_epsilon`. It is the metric SPEC's numeric-exact-match "
            "acceptance criteria name, and it is deliberately *not* `strict match`: the "
            "latter compares normalized strings and scores `$1,234.50` against `1234.5` as a "
            "miss. Neither is a correctness verdict, and their biases run in opposite "
            "directions — `strict match` under-credits valid paraphrases, while numeric "
            "exact match is a presence test that cannot tell whether a figure was *used* "
            "correctly and can be satisfied by a verbose answer reciting many numbers. Read "
            "them together, and treat neither as an LLM-judge result. Rows whose reference "
            "holds no quantity, including every `unanswerable` row, are out of scope rather "
            "than scored as failures.",
            "",
            "Every rate divides by the number of golden examples in its population, so a row "
            "that failed to produce an answer counts as a miss rather than shrinking the "
            "denominator.",
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


def rescore_receipt(
    answers_path: Path,
    examples: list[QAExample],
    *,
    numeric_epsilon: float,
) -> tuple[dict[str, float], list[dict]]:
    """Recompute scores for a committed `_answers.json` without re-running inference.

    Receipts store the full `Answer`, so every score in `score_answer` is
    recoverable offline.  That is what makes a metric added after a run —
    per-category rates, numeric exact-match — applicable to the baseline it has to
    be compared against, instead of forcing a re-run or a hand-computed number.

    Rows are rescored rather than read: a receipt written before a metric existed
    has no field for it, and trusting the stored value would silently mix scorer
    versions across the comparison.
    """
    rows = json.loads(answers_path.read_text())
    by_id = {example.id: example for example in examples}
    unknown = sorted({str(row["example_id"]) for row in rows} - by_id.keys())
    if unknown:
        raise ValueError(
            f"{answers_path.name} scores examples absent from this golden set: "
            + ", ".join(unknown[:5])
        )
    rescored: list[dict] = []
    for row in rows:
        example = by_id[str(row["example_id"])]
        if row.get("error"):
            rescored.append({**row, "category": example.category})
            continue
        answer = Answer.model_validate(row["answer"])
        rescored.append(
            {**row, **score_answer(example, answer, numeric_epsilon=numeric_epsilon)}
        )
    return category_metrics(examples, rescored), rescored


def write_rescore_report(
    scored: dict[str, dict[str, float]],
    categories: list[str],
    output_path: Path,
    *,
    golden_set_hash: str,
    epsilon: float,
) -> None:
    lines = [
        "# Per-category baseline (recomputed, no inference re-run)",
        "",
        "Generated by `python -m vaultledger.evals rescore`. **Not a run manifest.** Every "
        "number here is recomputed offline from the committed `_answers.json` receipts named "
        "below, using `vaultledger.evals.matrix.score_answer` — the same scorer the live "
        "matrix calls, so a future variant-D cell is comparable to this table by construction.",
        "",
        "The source receipts were written before these metrics existed and have deliberately "
        "**not** been rewritten: a manifest must keep reporting what its own run computed.",
        "",
        f"Golden set hash: `{golden_set_hash}` · numeric epsilon: `{epsilon}`",
        "",
        "| Receipt | Category | N | Strict match | Numeric exact match |",
        "|---|---|---:|---:|---:|",
    ]
    for name, metrics in scored.items():
        for category in categories:
            count = metrics.get(f"matrix_examples__{category}")
            if count is None:
                continue
            numeric_n = int(metrics.get(f"numeric_exact_match_examples__{category}", 0.0))
            rate = metrics.get(f"numeric_exact_match_rate__{category}")
            numeric = f"{rate:.1%} (n={numeric_n})" if rate is not None else "— (none in scope)"
            lines.append(
                f"| `{name}` | `{category}` | {int(count)} | "
                f"{metrics[f'strict_answer_match_rate__{category}']:.1%} | {numeric} |"
            )
    lines.extend(
        [
            "",
            "Rows that failed to produce an answer are counted as misses in their category, "
            "never removed from the denominator. Numeric exact-match has its own denominator: "
            "references carrying no quantity are out of scope rather than scored as failures, "
            "and a category with nothing in scope shows an em dash rather than 0%.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines))


def run_rescore(args: Namespace) -> int:
    cfg = load_config()
    golden = load_golden_set(args.golden)
    epsilon = cfg.thresholds.numeric_epsilon
    report: dict[str, dict[str, float]] = {}
    for raw in args.answers:
        path = Path(raw)
        metrics, _ = rescore_receipt(path, golden.examples, numeric_epsilon=epsilon)
        report[path.name] = metrics
    if getattr(args, "report", ""):
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_rescore_report(
            report,
            sorted({example.category for example in golden.examples}),
            report_path,
            golden_set_hash=golden_hash(args.golden),
            epsilon=epsilon,
        )
    print(
        json.dumps(
            {
                "golden_set_hash": golden_hash(args.golden),
                "numeric_epsilon": epsilon,
                "scorer": "vaultledger.evals.matrix.score_answer",
                "note": (
                    "recomputed offline from committed receipts; no inference was re-run"
                ),
                "receipts": report,
            },
            indent=2,
        )
    )
    return 0


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

    # Phase 13 ablation arm. Default "off" preserves the meaning of every
    # manifest committed before the guards existed; "on" measures the stack the
    # product actually ships. Which arm becomes canonical is a Phase 17 decision,
    # deliberately not made silently by changing this default.
    guardrails_on = getattr(args, "guardrails", "off") == "on"
    guardrail_toggles = GuardrailToggles.from_config(cfg.guardrails) if guardrails_on else None
    records_db = cfg.repo_path(cfg.paths.index_dir) / "records.db" if guardrails_on else None
    if guardrails_on and not records_db.exists():
        raise RuntimeError(
            f"--guardrails on needs the record-of-truth database at {records_db}; run make ingest"
        )

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
                guardrail_toggles=guardrail_toggles,
                records_db=records_db,
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


__all__ = [
    "category_metrics",
    "numeric_exact_match",
    "numeric_reference_quantities",
    "rescore_receipt",
    "run_matrix",
    "run_rescore",
    "score_answer",
    "strict_answer_match",
    "write_matrix_report",
    "write_rescore_report",
]
