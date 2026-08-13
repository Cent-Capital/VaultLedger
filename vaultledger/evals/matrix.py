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
from xml.sax.saxutils import escape

from vaultledger.config import CONFIG_PATH, Config, load_config
from vaultledger.evals.golden import golden_hash, load_golden_set
from vaultledger.evals.judge import JudgeItem, judge_item
from vaultledger.gateway import GatewayTotals, LiteLLMGenerator
from vaultledger.generate import answer_question_agentic, answer_question_reliable
from vaultledger.generate.ollama import ollama_model_metadata, ollama_warm_model
from vaultledger.guardrails import GuardrailToggles
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.ingest.pipeline import assert_evaluation_corpus
from vaultledger.retrieve import (
    AgenticRetriever,
    CrossEncoderReranker,
    HybridRetriever,
    LightRAGRetriever,
    NaiveDenseRetriever,
)
from vaultledger.schemas import (
    Answer,
    DecodingProfile,
    MatrixJudgeVerdict,
    ModelMetadata,
    QAExample,
    RoutingDecision,
    RunManifest,
)

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


def _float_slug(value: float) -> str:
    return f"{value:g}".replace("-", "m").replace(".", "p")


def _gib(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GiB"


def _decoding_text(manifest: RunManifest) -> str:
    if manifest.decoding is None:
        return "—"
    cap = f", max={manifest.decoding.max_tokens}" if manifest.decoding.max_tokens else ""
    return f"t={manifest.decoding.temperature:g}, p={manifest.decoding.top_p:g}{cap}"


def _manifest_sort_key(manifest: RunManifest) -> tuple:
    decoding = manifest.decoding
    return (
        manifest.model,
        manifest.variant,
        decoding.temperature if decoding else -1.0,
        decoding.top_p if decoding else -1.0,
    )


def _canonical(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.]+", " ", text.casefold()).split())


def strict_answer_match(example: QAExample, answer: Answer) -> tuple[bool, str]:
    """Conservative deterministic score used until Phase 18's judged bake-off.

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
    if {"B_hybrid", "D_agentic"} & set(variants):
        required.append(index_dir / "bm25.json")
    if "C_graph" in variants:
        graph_dir = cfg.repo_path(cfg.graph.working_dir)
        required.extend(
            [
                graph_dir / "graph_chunk_entity_relation.graphml",
                graph_dir / "vdb_entities.json",
                graph_dir / "vdb_relationships.json",
                graph_dir / "vdb_chunks.json",
            ]
        )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "missing index artifacts; run `make data && make ingest` first: "
            + ", ".join(missing)
        )
    assert_evaluation_corpus(index_dir)


def _retrievers(cfg: Config, variants: list[str]) -> dict[str, object]:
    unsupported = sorted(set(variants) - {"A_naive", "B_hybrid", "C_graph", "D_agentic"})
    if unsupported:
        raise ValueError(
            f"variants not built yet: {', '.join(unsupported)}; "
            "built variants are A_naive/B_hybrid/C_graph/D_agentic"
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
    if "C_graph" in variants:
        built["C_graph"] = LightRAGRetriever.from_config(cfg)
    if {"B_hybrid", "D_agentic"} & set(variants):
        reranker = (
            CrossEncoderReranker(cfg.reranker.model, cfg.reranker.batch_size)
            if cfg.reranker.enabled
            else None
        )
        hybrid = HybridRetriever(
            index_dir,
            embedder,
            candidate_k=cfg.retrieval.candidate_k,
            rank_constant=cfg.retrieval.rrf_constant,
            reranker=reranker,
        )
        if "B_hybrid" in variants:
            built["B_hybrid"] = hybrid
        if "D_agentic" in variants:
            built["D_agentic"] = AgenticRetriever(
                hybrid,
                index_dir / "records.db",
            )
    return built


def _answer_top_n(
    cfg: Config,
    variant: str,
    *,
    graph_answer_top_n: int | None = None,
) -> int:
    """Resolve the declared generation-context budget for one matrix arm."""
    if variant == "C_graph":
        return graph_answer_top_n or cfg.graph.answer_top_n
    return cfg.retrieval.answer_top_n


def _reported_context_top_n(
    manifest: RunManifest,
    cfg: Config,
    current_config_hash: str,
) -> int | None:
    """Read context k from a receipt, or safely recover a pre-field default."""
    recorded = manifest.metrics.get("retrieval_answer_top_n")
    if recorded is not None:
        return int(recorded)
    if manifest.config_hash == current_config_hash:
        return _answer_top_n(cfg, manifest.variant)
    return None


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
    wall_latencies = [float(row["wall_latency_ms"]) for row in completed]
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
    metrics = {
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
        "median_wall_latency_ms": (
            round(float(median(wall_latencies)), 3) if wall_latencies else 0.0
        ),
        "p95_wall_latency_ms": round(_percentile(wall_latencies, 0.95), 3),
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
    judged = [row for row in completed if row.get("judge")]
    if judged:
        judge_calls = [row.get("judge_gateway", {}) for row in judged]
        metrics.update(
            {
                "judge_coverage_rate": len(judged) / n if n else 0.0,
                "judge_pass_rate": _rate(
                    [row["judge"] for row in judged], "passed", n
                ),
                "judge_calls": float(
                    sum(int(call.get("calls", 0)) for call in judge_calls)
                ),
                "judge_input_tokens": float(
                    sum(int(call.get("input_tokens", 0)) for call in judge_calls)
                ),
                "judge_output_tokens": float(
                    sum(int(call.get("output_tokens", 0)) for call in judge_calls)
                ),
                "judge_latency_ms": round(
                    sum(float(call.get("latency_ms", 0.0)) for call in judge_calls),
                    3,
                ),
            }
        )
    agent_rows = [
        row
        for row in completed
        if row.get("answer", {}).get("variant") == "D_agentic"
    ]
    if agent_rows:
        step_counts = [len(row["answer"]["agent_steps"]) for row in agent_rows]
        token_counts = [
            sum(int(step["tokens_used"]) for step in row["answer"]["agent_steps"])
            for row in agent_rows
        ]
        metrics.update(
            {
                "agent_trace_coverage_rate": _rate(
                    agent_rows, "agent_trace_complete", n
                ),
                "agent_step_budget_compliance_rate": _rate(
                    agent_rows, "agent_steps_within_budget", n
                ),
                "agent_token_budget_compliance_rate": _rate(
                    agent_rows, "agent_tokens_within_budget", n
                ),
                "agent_exhaustion_rate": _rate(agent_rows, "agent_exhausted", n),
                "agent_average_steps": sum(step_counts) / len(step_counts),
                "agent_max_steps": float(max(step_counts, default=0)),
                "agent_average_trace_tokens": sum(token_counts) / len(token_counts),
            }
        )
    return metrics


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
    graph_answer_top_n: int | None = None,
    guardrail_toggles: GuardrailToggles | None = None,
    records_db: Path | None = None,
    temperature: float,
    top_p: float,
    judge_model: str | None = None,
) -> tuple[Path, Path]:
    generator = LiteLLMGenerator(
        model,
        base_url=cfg.embedding.ollama_url,
        temperature=temperature,
        top_p=top_p,
        seed=cfg.seed,
        num_ctx=cfg.generation.num_ctx,
        max_tokens=cfg.generation.output_tokens_max,
        timeout=cfg.generation.request_timeout_seconds,
    )
    if not generator.is_available():
        raise RuntimeError(f"matrix model {model!r} is unavailable in Ollama")
    ollama_warm_model(
        model,
        base_url=cfg.embedding.ollama_url,
        temperature=temperature,
        top_p=top_p,
        seed=cfg.seed,
        num_ctx=cfg.generation.num_ctx,
        timeout=cfg.generation.request_timeout_seconds,
    )

    slug = re.sub(r"[^a-z0-9]+", "_", model.casefold()).strip("_")
    arm = "on" if guardrail_toggles is not None else "off"
    answer_top_n = _answer_top_n(
        cfg,
        variant,
        graph_answer_top_n=graph_answer_top_n,
    )
    budget_suffix = f"_k{answer_top_n}" if graph_answer_top_n is not None else ""
    decoding_suffix = f"_t{_float_slug(temperature)}_p{_float_slug(top_p)}"
    checkpoint_path = (
        out_dir
        / (
            f".matrix_checkpoint_{slug}_{variant.casefold()}_{arm}"
            f"{budget_suffix}{decoding_suffix}.json"
        )
    )
    checkpoint_key = {
        "model": model,
        "variant": variant,
        "config_hash": _config_hash(),
        "golden_set_hash": golden_set_hash,
        # The guard arm is part of the key: an off-arm checkpoint must never be
        # resumed into an on-arm run, or the cell would mix two pipelines.
        "guardrails": arm,
        "retrieval_answer_top_n": answer_top_n,
        "temperature": temperature,
        "top_p": top_p,
        "seed": cfg.seed,
        "num_ctx": cfg.generation.num_ctx,
        "max_tokens": cfg.generation.output_tokens_max,
        "judge_model": judge_model,
        "example_ids": [example.id for example in examples],
    }
    rows: list[dict] = []
    model_metadata = None
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if all(checkpoint.get(key) == value for key, value in checkpoint_key.items()):
            rows = list(checkpoint.get("rows", []))
            if checkpoint.get("model_metadata"):
                model_metadata = ModelMetadata.model_validate(
                    checkpoint["model_metadata"]
                )
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
            reason="Phase 18 local matrix cell: model and decoding pinned by the manifest",
            est_cost_usd=0.0,
            actual_cost_usd=0.0,
        )
        try:
            if variant == "D_agentic":
                answer = answer_question_agentic(
                    example.question,
                    retriever,  # type: ignore[arg-type]
                    generator,
                    model_id=model,
                    max_steps=cfg.loops.agent_steps_max,
                    token_budget=cfg.loops.agent_tokens_max,
                    output_tokens_max=cfg.loops.agent_output_tokens_max,
                    seconds_budget=cfg.loops.agent_seconds_max,
                    k=answer_top_n,
                    min_snippet_chars=cfg.generation.min_snippet_chars,
                    routing=routing,
                    guardrail_toggles=guardrail_toggles,
                    records_db=records_db,
                    numeric_epsilon=cfg.thresholds.numeric_epsilon,
                )
            else:
                answer = answer_question_reliable(
                    example.question,
                    retriever,  # type: ignore[arg-type]
                    generator,
                    model_id=model,
                    k=answer_top_n,
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
        agent_budget_exhausted = any(
            event.guard == "agent_budget" for event in answer.guardrail_events
        )
        if agent_budget_exhausted:
            failure = {
                "example_id": example.id,
                "taxonomy_code": "TOOL_ERR",
                "note": "agent exhausted a configured budget and safely abstained",
            }
        elif not abstention_correct:
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
                "note": f"strict deterministic scorer: {reason}",
            }
        elif not citation_hit:
            failure = {
                "example_id": example.id,
                "taxonomy_code": "CITE_FAIL",
                "note": "no cited document matched the golden expected documents",
            }
        agent_metrics: dict[str, bool] = {}
        if answer.variant == "D_agentic":
            steps = answer.agent_steps
            agent_metrics = {
                "agent_trace_complete": (
                    [step.step for step in steps] == list(range(1, len(steps) + 1))
                    and all(step.output_summary.strip() for step in steps)
                ),
                "agent_steps_within_budget": len(steps) <= cfg.loops.agent_steps_max,
                "agent_tokens_within_budget": (
                    sum(step.tokens_used for step in steps) <= cfg.loops.agent_tokens_max
                ),
                "agent_exhausted": agent_budget_exhausted,
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
                **agent_metrics,
                "failure": failure,
            }
        )
        checkpoint_path.write_text(json.dumps({**checkpoint_key, "rows": rows}, indent=2))
        print(
            f"matrix checkpoint: {model} × {variant} {len(rows)}/{len(examples)}",
            flush=True,
        )

    # Capture the candidate's resident bytes while it is still the loaded model;
    # judging happens as a second block to avoid alternating model loads on every
    # row. The six-model run would otherwise spend most of its time thrashing
    # qwen3:8b (judge) in and out between candidate calls.
    if model_metadata is None:
        model_metadata = ollama_model_metadata(
            model,
            base_url=cfg.embedding.ollama_url,
        )
        checkpoint_path.write_text(
            json.dumps(
                {
                    **checkpoint_key,
                    "model_metadata": model_metadata.model_dump(),
                    "rows": rows,
                },
                indent=2,
            )
        )

    if judge_model:
        judge_generator = LiteLLMGenerator(
            judge_model,
            base_url=cfg.embedding.ollama_url,
            temperature=cfg.generation.temperature,
            top_p=cfg.generation.top_p,
            seed=cfg.seed,
            num_ctx=cfg.generation.num_ctx,
            max_tokens=cfg.generation.output_tokens_max,
            timeout=cfg.generation.request_timeout_seconds,
        )
        if not judge_generator.is_available():
            raise RuntimeError(f"matrix judge model {judge_model!r} is unavailable in Ollama")
        examples_by_id = {example.id: example for example in examples}
        for row in rows:
            if row.get("error") or row.get("judge"):
                continue
            answer = Answer.model_validate(row["answer"])
            evidence = "\n".join(
                f"[{citation.doc_id} page {citation.page}] {citation.snippet}"
                for citation in answer.citations
            ) or "No candidate citations were supplied."
            item = JudgeItem(
                id=str(row["example_id"]),
                question=examples_by_id[str(row["example_id"])].question,
                reference_answer=str(row["expected_answer"]),
                evidence=evidence,
                candidate_answer=answer.answer_text,
                human_pass=False,
            )
            before = judge_generator.snapshot()
            try:
                verdict = judge_item(judge_generator, item)
            except Exception as exc:
                row["judge_error"] = str(exc)
                checkpoint_path.write_text(
                    json.dumps(
                        {
                            **checkpoint_key,
                            "model_metadata": model_metadata.model_dump(),
                            "rows": rows,
                        },
                        indent=2,
                    )
                )
                continue
            usage = judge_generator.snapshot().delta(before)
            row["judge"] = {
                "example_id": item.id,
                **verdict.model_dump(),
            }
            row["judge_gateway"] = {
                "calls": usage.calls,
                "latency_ms": usage.latency_ms,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": usage.cost_usd,
            }
            checkpoint_path.write_text(
                json.dumps(
                    {
                        **checkpoint_key,
                        "model_metadata": model_metadata.model_dump(),
                        "rows": rows,
                    },
                    indent=2,
                )
            )

    order = {example.id: index for index, example in enumerate(examples)}
    rows.sort(key=lambda row: order[str(row["example_id"])])
    totals = _totals_from_rows(rows)
    metrics = _cell_metrics(examples, rows, totals)
    metrics["retrieval_answer_top_n"] = float(answer_top_n)
    metrics["model_prewarmed"] = 1.0
    # Self-describing arm: a manifest must say which guard stack produced it, or
    # on-arm and off-arm cells become silently incomparable in the matrix.
    metrics["guardrails_enabled"] = 1.0 if guardrail_toggles is not None else 0.0
    failures = [row["failure"] for row in rows if row.get("failure")]
    failures.extend(
        {
            "example_id": row["example_id"],
            "taxonomy_code": "TOOL_ERR",
            "note": f"judge failed: {row['judge_error']}",
        }
        for row in rows
        if row.get("judge_error")
    )
    judge_verdicts = [
        MatrixJudgeVerdict.model_validate(row["judge"])
        for row in rows
        if row.get("judge")
    ]
    completed_rows = [row for row in rows if not row.get("error")]
    if judge_model and len(judge_verdicts) != len(completed_rows):
        raise RuntimeError(
            f"judge coverage incomplete for {model} × {variant}: "
            f"{len(judge_verdicts)}/{len(completed_rows)} completed rows; "
            f"checkpoint retained at {checkpoint_path}"
        )
    manifest = RunManifest(
        run_id=(
            f"phase18_{slug}_{variant.casefold()}{budget_suffix}{decoding_suffix}_"
            f"{uuid4().hex[:12]}"
        ),
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
        decoding=DecodingProfile(
            temperature=temperature,
            top_p=top_p,
            seed=cfg.seed,
            num_ctx=cfg.generation.num_ctx,
            max_tokens=cfg.generation.output_tokens_max,
        ),
        model_metadata=model_metadata,
        judge_model=judge_model,
        judge_verdicts=judge_verdicts,
    )
    manifest_path = out_dir / f"{manifest.run_id}.json"
    answers_path = out_dir / f"{manifest.run_id}_answers.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    answers_path.write_text(json.dumps(rows, indent=2) + "\n")
    checkpoint_path.unlink(missing_ok=True)
    return manifest_path, answers_path


def write_latency_quality_frontier(
    manifest_paths: list[Path],
    output_path: Path,
) -> None:
    """Generate the Phase 18 descriptive scatter directly from manifests.

    Chart contract: model/decoding cell is the observation grain; x is median
    completed-row wall latency, y is judge pass rate when present (otherwise the
    literal-anchor rate), family is the two-color grouping, and bubble area
    approximates Ollama resident bytes. Six canonical model points are below the
    usual scatter-density threshold, but they are the complete decision set and
    every point is intentionally labelled; a finer grain would answer a
    different question.
    """
    manifests = [RunManifest.model_validate_json(path.read_text()) for path in manifest_paths]
    if not manifests:
        raise ValueError("cannot generate a latency-quality frontier without manifests")
    points = []
    for manifest in sorted(manifests, key=_manifest_sort_key):
        metric = manifest.metrics
        latency = float(metric.get("median_wall_latency_ms", 0.0))
        quality_key = (
            "judge_pass_rate"
            if "judge_pass_rate" in metric
            else "strict_answer_match_rate"
        )
        quality = float(metric[quality_key])
        metadata = manifest.model_metadata
        resident = metadata.resident_size_bytes if metadata else 0
        family = metadata.family if metadata else manifest.model.split("/", 1)[-1].split(":")[0]
        points.append((manifest, latency, quality, quality_key, resident, family))

    width, height = 1040, 650
    left, right, top, bottom = 90, 250, 95, 130
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_latency = max((point[1] for point in points), default=1.0) or 1.0
    max_resident = max((point[4] for point in points), default=1) or 1

    def x_pos(latency: float) -> float:
        return left + (latency / (max_latency * 1.1)) * plot_width

    def y_pos(quality: float) -> float:
        return top + (1.0 - quality) * plot_height

    def radius(resident: int) -> float:
        return 7.0 + 11.0 * math.sqrt(resident / max_resident) if resident else 7.0

    palette = {"qwen3": "#2563eb", "gemma3": "#d97706"}
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
            '<text x="90" y="36" font-size="22" font-weight="700">'
            'Local-model latency–quality frontier</text>'
        ),
        (
            f'<text x="90" y="62" font-size="13" class="muted">{len(points)} '
            'model × decoding cell(s) · bubble area ≈ resident bytes · '
            'direct labels identify every point</text>'
        ),
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = y_pos(tick)
        svg.extend(
            [
                (
                    f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" '
                    f'y2="{y:.1f}" class="grid"/>'
                ),
                (
                    f'<text x="{left - 14}" y="{y + 4:.1f}" font-size="12" '
                    f'text-anchor="end" class="mono muted">{tick:.0%}</text>'
                ),
            ]
        )
    for index in range(5):
        value = max_latency * 1.1 * index / 4
        x = x_pos(value)
        svg.extend(
            [
                (
                    f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
                    f'y2="{top + plot_height}" class="grid"/>'
                ),
                (
                    f'<text x="{x:.1f}" y="{top + plot_height + 24}" font-size="12" '
                    f'text-anchor="middle" class="mono muted">{value / 1000:.1f}s</text>'
                ),
            ]
        )
    svg.extend(
        [
            (
                f'<line x1="{left}" y1="{top + plot_height}" '
                f'x2="{left + plot_width}" y2="{top + plot_height}" class="axis"/>'
            ),
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" class="axis"/>',
            (
                f'<text x="{left + plot_width / 2:.1f}" '
                f'y="{top + plot_height + 58}" font-size="13" text-anchor="middle">'
                'Median wall latency per completed row</text>'
            ),
            (
                f'<text x="25" y="{top + plot_height / 2:.1f}" font-size="13" '
                f'text-anchor="middle" transform="rotate(-90 25 '
                f'{top + plot_height / 2:.1f})">Quality rate</text>'
            ),
        ]
    )
    for index, (manifest, latency, quality, quality_key, resident, family) in enumerate(points):
        x, y = x_pos(latency), y_pos(quality)
        root = (
            "qwen3"
            if "qwen" in family.casefold()
            else "gemma3"
            if "gemma" in family.casefold()
            else "other"
        )
        color = palette.get(root, "#667085")
        r = radius(resident)
        fill = color if root == "qwen3" else "#ffffff"
        label = manifest.model.removeprefix("ollama/")
        if len({item.model for item in manifests}) < len(manifests):
            label += f" ({_decoding_text(manifest)})"
        label_y = y + (4 if index % 2 == 0 else -8)
        title = (
            f"{manifest.model}; {quality_key}={quality:.1%}; "
            f"median wall={latency:.0f} ms; resident={_gib(resident) if resident else 'unknown'}"
        )
        svg.extend(
            [
                (
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" '
                    f'stroke="{color}" stroke-width="3"><title>{escape(title)}</title>'
                    '</circle>'
                ),
                (
                    f'<text x="{x + r + 7:.1f}" y="{label_y:.1f}" font-size="12" '
                    f'font-weight="600">{escape(label)}</text>'
                ),
                (
                    f'<text x="{x + r + 7:.1f}" y="{label_y + 16:.1f}" '
                    f'font-size="11" class="mono muted">{quality:.1%} · '
                    f'{latency / 1000:.1f}s</text>'
                ),
            ]
        )
    legend_x = left + plot_width + 50
    svg.extend(
        [
            f'<text x="{legend_x}" y="{top + 8}" font-size="12" font-weight="700">Family</text>',
            (
                f'<circle cx="{legend_x + 7}" cy="{top + 32}" r="7" '
                'fill="#2563eb" stroke="#2563eb" stroke-width="2"/>'
            ),
            f'<text x="{legend_x + 24}" y="{top + 36}" font-size="12">Qwen3</text>',
            (
                f'<circle cx="{legend_x + 7}" cy="{top + 58}" r="7" '
                'fill="#ffffff" stroke="#d97706" stroke-width="3"/>'
            ),
            f'<text x="{legend_x + 24}" y="{top + 62}" font-size="12">Gemma 3</text>',
            (
                f'<text x="{legend_x}" y="{top + 105}" font-size="12" '
                'font-weight="700">Size encoding</text>'
            ),
            (
                f'<circle cx="{legend_x + 12}" cy="{top + 139}" r="12" '
                'fill="#ffffff" stroke="#667085" stroke-width="2"/>'
            ),
            (
                f'<text x="{legend_x + 34}" y="{top + 143}" font-size="11" '
                'class="muted">larger bubble =</text>'
            ),
            (
                f'<text x="{legend_x + 34}" y="{top + 158}" font-size="11" '
                'class="muted">more resident bytes</text>'
            ),
            (
                '<rect x="70" y="565" width="900" height="58" rx="8" '
                'fill="#f8fafc" stroke="#d0d5dd"/>'
            ),
            (
                '<text x="90" y="589" font-size="12" font-weight="700">'
                'Descriptive only — not a latency ranking</text>'
            ),
            (
                '<text x="90" y="609" font-size="11" class="muted">'
                'Phase 13 saw ~50% p50 movement between runs with byte-identical answers. '
                'Machine load can move points more than the apparent model gap.</text>'
            ),
            '</svg>',
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(svg) + "\n")


def write_matrix_report(
    manifest_paths: list[Path],
    output_path: Path,
    *,
    frontier_path: Path | None = None,
) -> None:
    manifests = [RunManifest.model_validate_json(path.read_text()) for path in manifest_paths]
    if not manifests:
        raise ValueError("cannot generate a model matrix without manifests")
    hashes = {manifest.golden_set_hash for manifest in manifests}
    if len(hashes) != 1:
        raise ValueError("matrix manifests use different golden sets")
    total_cost = sum(manifest.total_cost_usd for manifest in manifests)
    model_count = len({manifest.model for manifest in manifests})
    report_cfg = load_config()
    current_config_hash = _config_hash()
    lines = [
        "# Model matrix",
        "",
        "Manifest-backed comparison over the explicitly selected model, variants, and golden-set "
        "population. This report does not generalize beyond those cells.",
        "",
        f"Golden set hash: `{manifests[0].golden_set_hash}`",
        f"Cells: **{len(manifests)}** across **{model_count} model(s)**",
        f"Total measured API spend: **${total_cost:.6f}** (local models are unpriced, not free)",
        "",
        "| Model | Params | Quant | Resident | Variant | Decoding | Context k | N | Judge pass | "
        "Strict match | Numeric exact match | Citation hit | Abstention accuracy | Wall p50 | "
        "Wall p95 | Gateway p50 | Gateway p95 | Tokens in / out | Cost | Manifest |",
        "|---|---:|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if frontier_path is not None:
        try:
            frontier_ref = frontier_path.relative_to(output_path.parent)
        except ValueError:
            frontier_ref = frontier_path
        lines[8:8] = [
            "## Latency–quality frontier",
            "",
            "This harness-generated scatter is descriptive, not a latency ranking; the "
            "Phase 13 instability caveat is embedded in the SVG.",
            "",
            f"![Latency–quality frontier]({frontier_ref})",
            "",
        ]
    for manifest in sorted(manifests, key=_manifest_sort_key):
        metric = manifest.metrics
        # Manifests written before this metric existed are shown as "—" rather
        # than back-filled with a zero that would read as a measured failure.
        numeric_n = int(metric.get("numeric_exact_match_examples", 0.0))
        numeric = (
            f"{metric['numeric_exact_match_rate']:.1%} (n={numeric_n})" if numeric_n else "—"
        )
        wall_p50 = metric.get("median_wall_latency_ms")
        wall_p95 = metric.get("p95_wall_latency_ms")
        wall_p50_text = f"{wall_p50:.0f} ms" if wall_p50 is not None else "—"
        wall_p95_text = f"{wall_p95:.0f} ms" if wall_p95 is not None else "—"
        context_top_n = _reported_context_top_n(
            manifest,
            report_cfg,
            current_config_hash,
        )
        context_top_n_text = str(context_top_n) if context_top_n is not None else "—"
        metadata = manifest.model_metadata
        params = metadata.parameter_count if metadata else "—"
        quantization = metadata.quantization if metadata else "—"
        resident = _gib(metadata.resident_size_bytes) if metadata else "—"
        judge_pass = (
            f"{metric['judge_pass_rate']:.1%}"
            if "judge_pass_rate" in metric
            else "—"
        )
        lines.append(
            "| "
            f"`{manifest.model}` | {params} | `{quantization}` | {resident} | "
            f"`{manifest.variant}` | {_decoding_text(manifest)} | {context_top_n_text} | "
            f"{int(metric['matrix_examples'])} | "
            f"{judge_pass} | "
            f"{metric['strict_answer_match_rate']:.1%} | "
            f"{numeric} | "
            f"{metric['citation_doc_hit_rate']:.1%} | "
            f"{metric['abstention_accuracy']:.1%} | "
            f"{wall_p50_text} | "
            f"{wall_p95_text} | "
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
                "Category-scoped acceptance criteria must be read from this table rather than "
                "inferred from the aggregate row. `Numeric` is scored only over rows whose "
                "reference carries a numeric quantity; its `n` differs from the category `n` "
                "for that reason, and a blank cell means no row in that category is in scope.",
                "",
                "| Model | Variant | Decoding | Context k | Category | N | Strict match | "
                "Numeric exact match | Citation hit | Abstention accuracy |",
                "|---|---|---|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        for manifest in sorted(manifests, key=_manifest_sort_key):
            metric = manifest.metrics
            context_top_n = _reported_context_top_n(
                manifest,
                report_cfg,
                current_config_hash,
            )
            context_top_n_text = str(context_top_n) if context_top_n is not None else "—"
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
                    f"`{manifest.model}` | `{manifest.variant}` | "
                    f"{_decoding_text(manifest)} | {context_top_n_text} | "
                    f"`{category}` | "
                    f"{int(count)} | "
                    f"{metric[f'strict_answer_match_rate__{category}']:.1%} | "
                    f"{numeric} | "
                    f"{metric[f'citation_doc_hit_rate__{category}']:.1%} | "
                    f"{metric[f'abstention_accuracy__{category}']:.1%} |"
                )
    metadata_by_model = {
        manifest.model: manifest.model_metadata
        for manifest in manifests
        if manifest.model_metadata is not None
    }
    if metadata_by_model:
        lines.extend(
            [
                "",
                "## Model identity and size",
                "",
                "Parameter count and quantisation come from Ollama `show`; the digest and "
                "artifact bytes come from installed tags; resident bytes come from Ollama "
                "`ps` while that candidate was loaded. Tag numbers are never treated as "
                "parameter counts.",
                "",
                "| Model | Family | Parameters | Quantisation | Digest | Artifact | "
                "Resident | VRAM | Ollama |",
                "|---|---|---:|---|---|---:|---:|---:|---|",
            ]
        )
        for model, metadata in sorted(metadata_by_model.items()):
            assert metadata is not None
            lines.append(
                f"| `{model}` | `{metadata.family}` | {metadata.parameter_count} | "
                f"`{metadata.quantization}` | `{metadata.digest}` | "
                f"{_gib(metadata.artifact_size_bytes)} | "
                f"{_gib(metadata.resident_size_bytes)} | "
                f"{_gib(metadata.resident_size_vram_bytes)} | "
                f"`{metadata.ollama_version}` |"
            )

    judged_manifests = [manifest for manifest in manifests if manifest.judge_model]
    if judged_manifests:
        lines.extend(
            [
                "",
                "## Judge verdicts and reasons",
                "",
                "The fixed local judge applies the versioned rubric to each candidate answer. "
                "Every verdict, including its `reason`, is stored in the RunManifest. The "
                "lists below surface every failed verdict plus up to three passing examples "
                "per cell; they are explanations to inspect, not independent ground truth.",
                "",
                "The 20-label validation supports only an at-least-83% judge-accuracy claim, "
                "and a null classifier scores 19/20 on that set. Judge pass rate is therefore "
                "read conjunctively with deterministic metrics under ADR-0014, never alone.",
            ]
        )
        for manifest in sorted(judged_manifests, key=_manifest_sort_key):
            verdicts = manifest.judge_verdicts
            failed = [verdict for verdict in verdicts if not verdict.passed]
            passed = [verdict for verdict in verdicts if verdict.passed]
            lines.extend(
                [
                    "",
                    f"### `{manifest.model}` · `{manifest.variant}` · {_decoding_text(manifest)}",
                    "",
                    f"Judge: `{manifest.judge_model}` · coverage "
                    f"{manifest.metrics.get('judge_coverage_rate', 0.0):.1%} · passes "
                    f"{len(passed)}/{int(manifest.metrics['matrix_examples'])}.",
                    "",
                ]
            )
            surfaced = failed + passed[:3]
            if not surfaced:
                lines.append("- No judge verdict was recorded; this cell is incomplete.")
            for verdict in surfaced:
                label = "PASS" if verdict.passed else "FAIL"
                reason = " ".join(verdict.reason.split())
                lines.append(
                    f"- `{verdict.example_id}` — **{label}** "
                    f"(`{verdict.failure_code}`): {reason}"
                )
    agent_manifests = [
        manifest
        for manifest in manifests
        if "agent_trace_coverage_rate" in manifest.metrics
    ]
    if agent_manifests:
        lines.extend(
            [
                "",
                "## Agent-loop controls",
                "",
                "**Trace coverage, step budget and token budget are invariants, not results.** "
                "The loop appends exactly one step per iteration over a fixed range and charges "
                "tokens through `min(..., budget - used)`, so all three read 100% by "
                "construction — a planner that never returns a valid action still scores 100% "
                "on every one. They are regression guards: if one ever drops, the loop's "
                "bookkeeping is broken. They are **not** evidence that the agent behaved well, "
                "and must never be reported as a measured safety property.",
                "",
                "`Exhausted` is the only column here that varies with model behaviour, and it "
                "is the one worth reading. Note that a wall-clock exhaustion caused by an "
                "unreachable generator is a transport failure, not a model failure; the two are "
                "labelled separately in the step trace (ADR-0007).",
                "",
                "Computed from the complete `AgentStep` arrays in each answer receipt. Rates "
                "divide by all golden examples in the cell, so a failed row stays a miss; the "
                "step and token averages divide only by rows that ran.",
                "",
                "| Model | Trace coverage | Step budget | Token budget | Exhausted | "
                "Average / max steps | Average traced tokens |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for manifest in sorted(agent_manifests, key=lambda item: item.model):
            metric = manifest.metrics
            lines.append(
                f"| `{manifest.model}` | {metric['agent_trace_coverage_rate']:.1%} | "
                f"{metric['agent_step_budget_compliance_rate']:.1%} | "
                f"{metric['agent_token_budget_compliance_rate']:.1%} | "
                f"{metric['agent_exhaustion_rate']:.1%} | "
                f"{metric['agent_average_steps']:.2f} / {metric['agent_max_steps']:.0f} | "
                f"{metric['agent_average_trace_tokens']:.0f} |"
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
            "Citation hit and abstention accuracy are not necessarily independent signals. On "
            "an answerable population where abstentions carry no citations and every answer that "
            "does not abstain cites an expected document, the two columns are structurally "
            "identical; inspect the row receipts before treating them as corroboration.",
            "",
            "`Context k` is read from the manifest when recorded. For older receipts predating "
            "that field, it is recovered only when the receipt's config hash exactly matches the "
            "current config; otherwise the report shows an em dash.",
            "",
            "`Strict match` is a deterministic literal-anchor scorer, not a lower bound: "
            "answerable rows must repeat the reference's amounts, dates, and identifiers; "
            "other rows require a normalized reference substring. It under-credits valid "
            "paraphrases, but can also over-credit a hedged answer that lists the right anchor "
            "among several wrong candidates. Per-example reasons and complete answers live "
            "beside each manifest in its `_answers.json` receipt.",
            "",
            "Wall latency covers the complete row, including retrieval, reranking, generation, "
            "repairs, and guardrails. Gateway latency covers completion calls only. Token counts "
            "come from provider usage when available and do not include retrieval-side embedding "
            "or keyword-extraction calls. Every displayed value is loaded from the RunManifests "
            "above, except the explicitly described config-hash recovery for historical context "
            "k; this file is generated, never hand-edited.",
            "",
            "Phase 18 candidate models are pre-warmed with `keep_alive=10m` before their cell. "
            "Warm-up time is outside row latency, preventing a one-time model load from becoming "
            "a quality timeout; judge-load time is likewise excluded from candidate latency.",
            "",
            "Every structured completion is capped at the manifest's `max` token count (768 in "
            "the preregistered run), and a 600-second request overrun remains an explicit "
            "`TOOL_ERR`. The cap and timeout are fixed controls, not swept settings.",
            "",
            "Unlike the rates above, median and p95 latency are computed over completed rows "
            "only: a row that failed to produce an answer is excluded from those statistics "
            "entirely rather than counted as slow. Latency denominators can therefore differ "
            "between arms in the same table, and an arm that timed out reports a tail that "
            "understates its observed worst case. Read the latency columns against each arm's "
            "coverage, and at small N treat p95 as the slowest completed row rather than a "
            "distribution.",
            "",
            "Phase 13 observed roughly 50% p50 movement between runs that produced "
            "byte-identical answers. This harness therefore cannot rank models by latency. "
            "The latency-quality frontier is a descriptive picture, not a model ordering or "
            "a tie-breaker.",
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
    decoding_sweep = bool(getattr(args, "decoding_sweep", False))
    judge_model = str(getattr(args, "judge_model", "") or "") or None
    decoding_profiles = [(cfg.generation.temperature, cfg.generation.top_p)]
    if decoding_sweep:
        if models != [cfg.matrix.decoding_sweep_model]:
            raise ValueError(
                "--decoding-sweep requires exactly the preregistered model "
                f"{cfg.matrix.decoding_sweep_model!r}"
            )
        decoding_profiles = [
            (temperature, top_p)
            for temperature in cfg.matrix.decoding_temperatures
            for top_p in cfg.matrix.decoding_top_ps
        ]
    graph_answer_top_n = getattr(args, "graph_answer_top_n", None)
    limit = cfg.matrix.smoke_limit if args.limit is None else args.limit
    if len(set(models)) != len(models):
        raise ValueError("matrix model ids must be unique")
    if len(set(variants)) != len(variants):
        raise ValueError("matrix variants must be unique")
    if len(set(decoding_profiles)) != len(decoding_profiles):
        raise ValueError("matrix decoding profiles must be unique")
    if graph_answer_top_n is not None:
        if graph_answer_top_n < 1:
            raise ValueError("--graph-answer-top-n must be at least 1")
        if "C_graph" not in variants:
            raise ValueError("--graph-answer-top-n requires C_graph in --variants")
    _required_inputs(cfg, variants)
    golden = load_golden_set(args.golden)
    categories = set(getattr(args, "categories", None) or [])
    population = [
        example
        for example in golden.examples
        if not categories or example.category in categories
    ]
    examples = population[:limit] if limit else population
    if not examples:
        raise ValueError("matrix selection contains no golden examples")
    retrievers = _retrievers(cfg, variants)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Phase 13 ablation arm. Default "off" preserves the meaning of every
    # manifest committed before the guards existed; "on" measures the stack the
    # product actually ships. Which arm becomes canonical is a Phase 18 decision,
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
            for temperature, top_p in decoding_profiles:
                manifest_path, answers_path = _run_cell(
                    cfg=cfg,
                    model=model,
                    variant=variant,
                    retriever=retrievers[variant],
                    examples=examples,
                    golden_set_hash=golden_hash(args.golden),
                    out_dir=out_dir,
                    graph_answer_top_n=(
                        graph_answer_top_n if variant == "C_graph" else None
                    ),
                    guardrail_toggles=guardrail_toggles,
                    records_db=records_db,
                    temperature=temperature,
                    top_p=top_p,
                    judge_model=judge_model,
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
    frontier_arg = str(getattr(args, "frontier", "") or "")
    frontier_path = (
        Path(frontier_arg)
        if frontier_arg
        else report_path.with_name(f"{report_path.stem}_frontier.svg")
    )
    write_latency_quality_frontier(paths, frontier_path)
    write_matrix_report(paths, report_path, frontier_path=frontier_path)
    print(
        json.dumps(
            {
                "report": str(report_path),
                "frontier": str(frontier_path),
                "manifests": [str(path) for path in paths],
                "answer_receipts": receipts,
                "models": models,
                "variants": variants,
                "decoding_profiles": [
                    {"temperature": temperature, "top_p": top_p}
                    for temperature, top_p in decoding_profiles
                ],
                "judge_model": judge_model,
                "graph_answer_top_n": graph_answer_top_n,
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
    "write_latency_quality_frontier",
    "write_rescore_report",
]
