"""Phase 19 cross-variant comparison, generated from committed receipts.

This module runs no cell and makes no model call. It reads run manifests and
answer receipts that are already committed, checks each one is the cell it claims
to be, and lays the A/B/C/D variants out with their population boundaries
visible.

Three rules drive the layout, and each of them exists because the obvious
alternative would have produced a false comparison:

1. **Arms are grouped by the population they were measured on.** A and B carry
   retrieval evidence over the 70 golden rows that have expected documents. D was
   measured on its 26 aggregation/multi-hop target rows. C was measured on six
   global-summary rows. Rendering one rectangle across those would invent a
   comparison that no run supports.
2. **Every generation number is recomputed here by one scorer version** from the
   committed ``_answers.json`` receipts, exactly as Phase 14's per-category
   baseline did. Receipts written before a metric existed have no field for it,
   and reading stored values would silently mix scorer versions across arms.
3. **A cell that was never measured stays blank and is named as unmeasured.** It
   is never filled in from a neighbouring population, a neighbouring model, or a
   rejected candidate.

Rule 3 has teeth: ``_assert_product_prompt`` rejects any declared generation cell
whose recorded prompt hash is not the shipped prompt. The Phase 19 evidence-first
candidate is a live trap here — it sits in ``reports/`` under a ``phase18_``
prefix with better abstention numbers than the cell that ships, and ADR-0019
rejected it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from argparse import Namespace
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vaultledger.config import REPO_ROOT, load_config
from vaultledger.evals.golden import DEFAULT_GOLDEN_PATH, golden_hash, load_golden_set
from vaultledger.evals.matrix import (
    _config_hash,
    _decoding_text,
    _git_sha,
    _prompt_hash_text,
    _reported_context_top_n,
    rescore_receipt,
)
from vaultledger.generate.reliable import PROMPT_SHA256
from vaultledger.schemas import QAExample, RunManifest

DEFAULT_REPORT = REPO_ROOT / "reports" / "variant_matrix.md"
DEFAULT_RECEIPT = REPO_ROOT / "receipts" / "phase19_variant_matrix.json"

#: ADR-0019 rejected this cell's prompt. It is named so a wrong declaration fails
#: with the reason rather than a generic hash mismatch.
REJECTED_CANDIDATE_RUN_ID = "phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_d5c5f885d0c9"


@dataclass(frozen=True)
class RetrievalArm:
    """One retrieval arm, bound to a committed Phase 3 or Phase 4 manifest."""

    label: str
    variant: str
    relative_path: str
    #: Metric prefix inside the manifest. The reranked and fusion-only arms are
    #: both recorded by the same Phase 4 run, so the fusion arm is read from its
    #: ``rrf_`` keys rather than from a separate run on an older golden set.
    prefix: str
    why: str


@dataclass(frozen=True)
class GenerationArm:
    """One generation arm, bound to a committed manifest and answer receipt."""

    label: str
    relative_path: str
    expected_rows: int
    why: str


@dataclass(frozen=True)
class Population:
    """A set of golden rows every arm in the group was measured on."""

    key: str
    title: str
    categories: tuple[str, ...]
    what_it_is: str
    arms: tuple[GenerationArm, ...]


RETRIEVAL_ARMS: tuple[RetrievalArm, ...] = (
    RetrievalArm(
        label="A_naive — dense only",
        variant="A_naive",
        relative_path="reports/phase3_c2a1ee76001e.json",
        prefix="",
        why="Phase 3 dense baseline, reproduced on the current golden set and config",
    ),
    RetrievalArm(
        label="B_hybrid — dense + BM25 + RRF, no reranker",
        variant="B_hybrid",
        relative_path="reports/phase4_1966922cebd9.json",
        prefix="rrf_",
        why="fusion-only arm recorded inside the same Phase 4 run as the shipped arm",
    ),
    RetrievalArm(
        label="B_hybrid — dense + BM25 + RRF + cross-encoder rerank (shipped)",
        variant="B_hybrid",
        relative_path="reports/phase4_1966922cebd9.json",
        prefix="",
        why="Phase 4 shipped retriever, reproduced on the current golden set and config",
    ),
)

GENERATION_POPULATIONS: tuple[Population, ...] = (
    Population(
        key="full_golden",
        title="Full golden set — 80 rows",
        categories=(
            "adversarial",
            "aggregation",
            "cross_persona",
            "global_summary",
            "guardrail_benign",
            "multi_hop",
            "single_doc",
            "unanswerable",
        ),
        what_it_is=(
            "Every golden row, guardrails on. Only B_hybrid was ever run at this "
            "population; A_naive has no generation cell at all, and C and D were "
            "scoped to their own target rows."
        ),
        arms=(
            GenerationArm(
                label="B_hybrid · qwen3:8b",
                relative_path=(
                    "reports/phase18_ollama_qwen3_8b_b_hybrid_t0_p0p95_c64ee5ca952f.json"
                ),
                expected_rows=80,
                why="Phase 18 canonical shipped-model cell on the shipped prompt",
            ),
        ),
    ),
    Population(
        key="agentic_targets",
        title="Variant-D target rows — 26 rows (aggregation + multi-hop)",
        categories=("aggregation", "multi_hop"),
        what_it_is=(
            "The two categories Phase 14 preregistered for the agentic loop. The "
            "B_hybrid arms are the contemporaneous Phase 11 baselines the Phase 14 "
            "acceptance criterion was written against, not the later Phase 18 cell."
        ),
        arms=(
            GenerationArm(
                label="B_hybrid · qwen3:8b",
                relative_path="reports/phase11_ollama_qwen3_8b_b_hybrid_eea876388398.json",
                expected_rows=80,
                why="Phase 14's declared 8B baseline; its 26 target rows are scored here",
            ),
            GenerationArm(
                label="D_agentic · qwen3:8b",
                relative_path="reports/phase11_ollama_qwen3_8b_d_agentic_4c9522233d68.json",
                expected_rows=26,
                why="Phase 14 agentic cell that met the improvement AC on the shipped model",
            ),
            GenerationArm(
                label="B_hybrid · qwen3:4b",
                relative_path="reports/phase11_ollama_qwen3_4b_b_hybrid_35d35e2fb62f.json",
                expected_rows=80,
                why="Phase 14's declared 4B baseline; its 26 target rows are scored here",
            ),
            GenerationArm(
                label="D_agentic · qwen3:4b",
                relative_path="reports/phase11_ollama_qwen3_4b_d_agentic_7163e731454e.json",
                expected_rows=26,
                why="Phase 14 agentic cell that regressed on 4B; the split result is kept",
            ),
        ),
    ),
    Population(
        key="global_summary",
        title="Global-summary rows — 6 rows",
        categories=("global_summary",),
        what_it_is=(
            "The corpus-wide questions Variant C was built for. Six rows is an "
            "underpowered comparison and ADR-0010 records the missed gate; read "
            "the arms as a direction, never as a ranking."
        ),
        arms=(
            GenerationArm(
                label="B_hybrid · qwen3:8b · context k=6",
                relative_path="reports/phase11_ollama_qwen3_8b_b_hybrid_4a099797b084.json",
                expected_rows=6,
                why="Phase 15's same-model B comparator",
            ),
            GenerationArm(
                label="C_graph · qwen3:8b · context k=12",
                relative_path="reports/phase11_ollama_qwen3_8b_c_graph_f3be41d85c23.json",
                expected_rows=6,
                why="Phase 15 graph arm at its default context budget",
            ),
            GenerationArm(
                label="C_graph · qwen3:8b · context k=6",
                relative_path="reports/phase11_ollama_qwen3_8b_c_graph_k6_e508b61b6bf6.json",
                expected_rows=6,
                why="the preregistered equal-context arm that left the comparison inconclusive",
            ),
        ),
    ),
)

#: Cells that were never measured. Naming them is the point: a blank in the
#: coverage map has to mean "not run", never "run and omitted".
UNMEASURED_CELLS: tuple[tuple[str, str, str], ...] = (
    (
        "A_naive",
        "generation, any population",
        "A is a retrieval baseline only. No A_naive generation cell was ever run, so "
        "no answer-quality number in this build is attributable to dense-only retrieval.",
    ),
    (
        "C_graph",
        "generation, full 80 rows",
        "Variant C was scoped to global-summary questions and its index build cost "
        "45.8 minutes of local inference for 60 documents. It was never run at full "
        "population.",
    ),
    (
        "D_agentic",
        "generation, full 80 rows",
        "The agentic loop was preregistered against aggregation and multi-hop rows "
        "only. Its aggregate figures describe those 26 rows and nothing wider.",
    ),
    (
        "C_graph / D_agentic",
        "retrieval-only metrics",
        "Recall, precision, MRR and hit rate were measured for the A and B retrievers. "
        "The graph and agentic paths were evaluated end to end, so no comparable "
        "retrieval-only row exists for them.",
    ),
)

#: Results quoted from the committed record rather than recomputed here, with the
#: file that carries each one. This generator reads manifests and answer
#: receipts; the Phase 15 graph-quality numbers live in a GraphML scorer whose
#: input is not a committed receipt, so they are carried as citations.
RECORDED_LIMITS: tuple[tuple[str, str, str], ...] = (
    (
        "Phase 15 entity recall: 11/15 = 73.3%",
        "decisions/ADR-0009-account-alias-scoring-and-distinct-entity-precision.md",
        "Below the preregistered 80% gate. ADR-0010 waives a gate that was measured "
        "and missed. A post-hoc account-alias rule scores 15/15, was written after "
        "seeing the strict result, and is recorded as a secondary diagnostic only.",
    ),
    (
        "Phase 15 distinct-entity precision: 11/81 = 13.6%",
        "decisions/ADR-0009-account-alias-scoring-and-distinct-entity-precision.md",
        "The more consequential of the two numbers for a privacy-first product.",
    ),
    (
        "Phase 15 fabricated account nodes",
        "PROGRESS.md, Phase 15 entry",
        "The local 8B extractor minted account identifiers from a ZIP code and from a "
        "net-pay amount, and two more appear nowhere in the corpus. An extractor that "
        "invents account numbers is a product finding, not a tuning detail.",
    ),
    (
        "Phase 15 B-vs-C comparison is underpowered",
        "PROGRESS.md, Phase 15 entry; ADR-0010",
        "Six global-summary rows. B is the provisional default; C is not shown to be "
        "worse than B by this run, and B is not shown to be better.",
    ),
    (
        "Phase 15 equal-context arm is inconclusive",
        "PROGRESS.md, Phase 15 entry",
        "C at k=6 landed between B and C at k=12, so the run cannot separate graph "
        "retrieval from context budget.",
    ),
    (
        "Phase 15 typed-relation recall: 0/15 = 0.0%",
        "PROGRESS.md, Phase 15 entry",
        "Near-uninformative. Ground truth uses typed predicates and LightRAG emits "
        "keyword bags, so exact triple matching cannot cross the vocabularies. Read "
        "it as a lower bound, never as 'no correct relations'.",
    ),
)


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


def _committed_paths() -> set[str]:
    return {line for line in _git("ls-files", "--", "reports").splitlines() if line}


def _load_manifest(relative_path: str, committed: set[str]) -> RunManifest:
    """Load one declared source, refusing anything not committed to the repo."""
    if relative_path not in committed:
        raise FileNotFoundError(
            f"{relative_path} is not committed; a generated comparison may only cite "
            "receipts that are in the repository"
        )
    return RunManifest.model_validate_json((REPO_ROOT / relative_path).read_text())


def _assert_product_prompt(manifest: RunManifest) -> None:
    """Refuse a generation cell that did not run the prompt the product ships.

    Manifests written before prompt hashing existed carry ``None``. That is the
    shipped prompt by construction: the only run that ever deviated is ADR-0019's
    candidate, and it is the run that introduced the field.
    """
    if manifest.prompt_sha256 is None:
        return
    if manifest.prompt_sha256 == PROMPT_SHA256:
        return
    if manifest.run_id == REJECTED_CANDIDATE_RUN_ID:
        raise ValueError(
            f"{manifest.run_id} is ADR-0019's rejected evidence-first candidate. Its "
            "numbers describe a prompt the product does not ship and must not appear "
            "in a variant comparison."
        )
    raise ValueError(
        f"{manifest.run_id} ran prompt {manifest.prompt_sha256}, not the shipped "
        f"prompt {PROMPT_SHA256}"
    )


def _answers_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path.replace(".json", "_answers.json")


def reproduction_count(
    manifest: RunManifest,
    committed: set[str],
) -> tuple[int, int]:
    """Count committed runs of the same arm that reproduce these exact metrics.

    Same arm means same variant, model and golden set. Returns
    ``(reproducing, comparable)``. This is the determinism claim stated as a
    count instead of an adjective.

    Runs are counted by ``run_id``, not by file. ``reports/`` carries pointer
    copies — ``phase3_baseline_latest.json`` is a byte copy of one dated
    manifest, and so is ``phase4_latest.json`` — and counting a file twice would
    inflate a reproduction claim with a duplicate of itself.
    """
    by_run_id: dict[str, RunManifest] = {}
    for relative in sorted(committed):
        if not relative.endswith(".json"):
            continue
        if relative.endswith(("_answers.json", "_answer.json", "_details.json", "_verdicts.json")):
            continue
        try:
            other = RunManifest.model_validate_json((REPO_ROOT / relative).read_text())
        except ValueError:
            continue
        if (other.variant, other.model, other.golden_set_hash) != (
            manifest.variant,
            manifest.model,
            manifest.golden_set_hash,
        ):
            continue
        by_run_id[other.run_id] = other
    reproducing = sum(
        1 for other in by_run_id.values() if other.metrics == manifest.metrics
    )
    return reproducing, len(by_run_id)


def score_arm(
    arm: GenerationArm,
    manifest: RunManifest,
    examples: list[QAExample],
    *,
    numeric_epsilon: float,
) -> dict[str, float]:
    """Recompute one arm's category rates from its committed answer receipt."""
    recorded_rows = int(manifest.metrics["matrix_examples"])
    if recorded_rows != arm.expected_rows:
        raise ValueError(
            f"{manifest.run_id} reports {recorded_rows} rows; the declaration for "
            f"{arm.label} expects {arm.expected_rows}"
        )
    answers = _answers_path(arm.relative_path)
    if not answers.exists():
        raise FileNotFoundError(f"{answers.name} is required to rescore {arm.label}")
    metrics, _ = rescore_receipt(answers, examples, numeric_epsilon=numeric_epsilon)
    return metrics


def _pct(metrics: dict[str, float], key: str) -> str:
    value = metrics.get(key)
    return f"{value:.1%}" if value is not None else "—"


def _numeric_cell(metrics: dict[str, float], category: str) -> str:
    in_scope = int(metrics.get(f"numeric_exact_match_examples__{category}", 0.0))
    if not in_scope:
        return "— (none in scope)"
    rate = metrics.get(f"numeric_exact_match_rate__{category}")
    return f"{rate:.1%} (n={in_scope})" if rate is not None else "— (none in scope)"


def _retrieval_section(
    arms: list[tuple[RetrievalArm, RunManifest]],
    committed: set[str],
    scored_rows: int,
    total_rows: int,
) -> list[str]:
    lines = [
        "## 1. Retrieval evidence — A vs B",
        "",
        f"Population: the **{scored_rows} of {total_rows}** golden rows that carry expected "
        "documents. Unanswerable rows have none by construction, so they are excluded here "
        "and scored by the generation evals instead. Every rate divides by those "
        f"{scored_rows} rows.",
        "",
        "| Arm | Variant | Recall@20 | Precision@20 | MRR | Hit rate | Manifest |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for arm, manifest in arms:
        metric = manifest.metrics
        p = arm.prefix
        lines.append(
            f"| {arm.label} | `{arm.variant}` | "
            f"{metric[f'{p}retrieval_recall@20']:.4f} | "
            f"{metric[f'{p}retrieval_precision@20']:.4f} | "
            f"{metric[f'{p}retrieval_mrr']:.4f} | "
            f"{metric[f'{p}retrieval_hit_rate']:.4f} | "
            f"`{manifest.run_id}` |"
        )
    dense = next(m for a, m in arms if a.variant == "A_naive")
    shipped = next(m for a, m in arms if a.variant == "B_hybrid" and not a.prefix)
    recall_delta = shipped.metrics["retrieval_recall@20"] - dense.metrics["retrieval_recall@20"]
    mrr_delta = shipped.metrics["retrieval_mrr"] - dense.metrics["retrieval_mrr"]
    lines.extend(
        [
            "",
            "### What separates the arms",
            "",
            f"Shipped hybrid retrieval moves recall@20 by **{recall_delta:+.4f}** and MRR by "
            f"**{mrr_delta:+.4f}** against the dense baseline. The two deltas are the finding: "
            "the dense retriever was already surfacing the right document inside the top 20 "
            "for almost every row, so fusion and reranking mostly **reorder** evidence rather "
            "than find more of it. Hit rate is identical across all three arms.",
            "",
            "That matters for how the result should be quoted. A recall number this high is a "
            "property of a 60-document synthetic corpus and a top-20 cutoff, not a claim about "
            "retrieval on a real library.",
            "",
            "### Reproduction",
            "",
            "| Arm | Runs with identical metrics | Comparable committed runs |",
            "|---|---:|---:|",
        ]
    )
    for arm, manifest in arms:
        if arm.prefix:
            continue
        reproducing, comparable = reproduction_count(manifest, committed)
        lines.append(f"| {arm.label} | {reproducing} | {comparable} |")
    lines.extend(
        [
            "",
            "Counted over every committed manifest sharing the arm's variant, model and "
            "golden-set hash. These runs span different config hashes and dates, so an "
            "identical metric set across them is evidence the retrieval path is deterministic "
            "rather than evidence that any one run was lucky.",
            "",
        ]
    )
    return lines


def _population_section(
    index: int,
    population: Population,
    arms: list[tuple[GenerationArm, RunManifest, dict[str, float]]],
    report_cfg: object,
    current_config_hash: str,
) -> list[str]:
    lines = [
        f"## {index}. Generation evidence: {population.title}",
        "",
        population.what_it_is,
        "",
        "| Arm | Variant | Model | Context k | Decoding | Prompt | Config hash | "
        "Receipt population | Manifest |",
        "|---|---|---|---:|---|---|---|---:|---|",
    ]
    for arm, manifest, _ in arms:
        context_top_n = _reported_context_top_n(manifest, report_cfg, current_config_hash)
        lines.append(
            f"| {arm.label} | `{manifest.variant}` | `{manifest.model}` | "
            f"{context_top_n if context_top_n is not None else '—'} | "
            f"{_decoding_text(manifest)} | {_prompt_hash_text(manifest)} | "
            f"`{manifest.config_hash[:12]}` | {int(manifest.metrics['matrix_examples'])} | "
            f"`{manifest.run_id}` |"
        )
    config_hashes = {manifest.config_hash for _, manifest, _ in arms}
    if len(config_hashes) > 1:
        lines.extend(
            [
                "",
                f"**These arms ran under {len(config_hashes)} different pipeline "
                "configurations.** The config hash column is not decoration: a difference "
                "there means the arms are not a controlled A/B, and any gap between them "
                "carries pipeline drift as well as variant effect.",
            ]
        )
    lines.extend(
        [
            "",
            "| Arm | Category | N | Strict match | Numeric exact match | Citation hit | "
            "Abstention accuracy |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for arm, _, metrics in arms:
        for category in population.categories:
            count = metrics.get(f"matrix_examples__{category}")
            if count is None:
                continue
            lines.append(
                f"| {arm.label} | `{category}` | {int(count)} | "
                f"{_pct(metrics, f'strict_answer_match_rate__{category}')} | "
                f"{_numeric_cell(metrics, category)} | "
                f"{_pct(metrics, f'citation_doc_hit_rate__{category}')} | "
                f"{_pct(metrics, f'abstention_accuracy__{category}')} |"
            )
    lines.append("")
    return lines


def build_report(
    *,
    golden_path: Path = DEFAULT_GOLDEN_PATH,
) -> tuple[str, dict]:
    """Render the cross-variant report and its provenance receipt."""
    cfg = load_config()
    current_config_hash = _config_hash()
    committed = _committed_paths()
    golden = load_golden_set(golden_path)
    examples = golden.examples
    expected_golden_hash = golden_hash(golden_path)

    retrieval: list[tuple[RetrievalArm, RunManifest]] = []
    sources: dict[str, dict] = {}
    for arm in RETRIEVAL_ARMS:
        manifest = _load_manifest(arm.relative_path, committed)
        retrieval.append((arm, manifest))
        sources[arm.relative_path] = {
            "sha256": _sha256(REPO_ROOT / arm.relative_path),
            "run_id": manifest.run_id,
            "variant": manifest.variant,
            "why": arm.why,
        }

    populations: list[tuple[Population, list[tuple[GenerationArm, RunManifest, dict]]]] = []
    generation_golden_hashes: set[str] = set()
    for population in GENERATION_POPULATIONS:
        scored: list[tuple[GenerationArm, RunManifest, dict]] = []
        for arm in population.arms:
            manifest = _load_manifest(arm.relative_path, committed)
            _assert_product_prompt(manifest)
            generation_golden_hashes.add(manifest.golden_set_hash)
            metrics = score_arm(
                arm,
                manifest,
                examples,
                numeric_epsilon=cfg.thresholds.numeric_epsilon,
            )
            scored.append((arm, manifest, metrics))
            answers = _answers_path(arm.relative_path)
            sources[arm.relative_path] = {
                "sha256": _sha256(REPO_ROOT / arm.relative_path),
                "answers_sha256": _sha256(answers),
                "run_id": manifest.run_id,
                "variant": manifest.variant,
                "population": population.key,
                "why": arm.why,
            }
        populations.append((population, scored))

    if generation_golden_hashes != {expected_golden_hash}:
        raise ValueError(
            "generation arms do not all use the current golden set: "
            + ", ".join(sorted(generation_golden_hashes))
        )

    scored_rows = sum(1 for example in examples if example.expected_doc_ids)
    generated_at = datetime.now(UTC).isoformat()
    git_sha = _git_sha()
    # Section numbers are derived, so adding a population cannot leave a stale
    # cross-reference pointing at the wrong table.
    unmeasured_index = 2 + len(GENERATION_POPULATIONS)
    limits_index = unmeasured_index + 1
    sources_index = limits_index + 1

    lines = [
        "# Variant matrix — A / B / C / D",
        "",
        "Generated by `python -m vaultledger.evals variant-matrix`. **Never hand-edited.** "
        "No cell is run here and no model is called: every figure is read from, or "
        "recomputed against, receipts already committed to this repository.",
        "",
        f"Golden set hash: `{expected_golden_hash}` · numeric epsilon: "
        f"`{cfg.thresholds.numeric_epsilon}` · repo `{git_sha[:12]}` · generated "
        f"{generated_at}",
        "",
        "## How to read this file",
        "",
        "The four variants were **not** measured on one common population, and this file "
        "does not pretend otherwise. Each section states the rows its arms share, and "
        "arms from different sections cannot be compared to each other. A blank is an "
        f"unmeasured cell, listed by name in section {unmeasured_index}.",
        "",
        "Every generation rate below is recomputed here from the committed "
        "`_answers.json` receipts by `vaultledger.evals.matrix.score_answer` — one scorer "
        "version across all arms. The source manifests are left reporting what their own "
        "runs computed; several predate the per-category and numeric metrics entirely, and "
        "reading their stored values would mix scorer versions across the comparison.",
        "",
        "Neither `strict match` nor `numeric exact match` is a correctness verdict. Strict "
        "match under-credits valid paraphrases. Numeric exact match is a presence test that "
        "cannot tell whether a figure was used correctly, and a verbose answer reciting many "
        "numbers can satisfy it. Read them together and treat neither as a judge result.",
        "",
        "## 0. Coverage map",
        "",
        "| Variant | Retrieval (70 rows) | Generation, 80 rows | Generation, 26 target rows "
        "| Generation, 6 global-summary rows |",
        "|---|---|---|---|---|",
        "| `A_naive` | measured | not measured | not measured | not measured |",
        "| `B_hybrid` | measured | measured | measured | measured |",
        "| `C_graph` | not measured | not measured | not measured | measured |",
        "| `D_agentic` | not measured | not measured | measured | not measured |",
        "",
    ]

    lines.extend(_retrieval_section(retrieval, committed, scored_rows, len(examples)))

    for index, (population, scored) in enumerate(populations, start=2):
        lines.extend(
            _population_section(index, population, scored, cfg, current_config_hash)
        )

    lines.extend(
        [
            f"## {unmeasured_index}. Cells that were never measured",
            "",
            "| Variant | Missing evidence | Why it is absent |",
            "|---|---|---|",
        ]
    )
    for variant, missing, why in UNMEASURED_CELLS:
        lines.append(f"| `{variant}` | {missing} | {why} |")

    lines.extend(
        [
            "",
            f"## {limits_index}. Recorded limits carried forward",
            "",
            "These are **quoted from the committed record, not recomputed by this "
            "generator**. They constrain how the tables above may be described, and none of "
            "them is upgraded here.",
            "",
            "| Recorded result | Source | What it constrains |",
            "|---|---|---|",
        ]
    )
    for result, source, constraint in RECORDED_LIMITS:
        lines.append(f"| {result} | `{source}` | {constraint} |")

    lines.extend(
        [
            "",
            f"## {sources_index}. Source receipts",
            "",
            "| Path | Run id | SHA-256 | Why this receipt |",
            "|---|---|---|---|",
        ]
    )
    for path in sorted(sources):
        entry = sources[path]
        lines.append(
            f"| `{path}` | `{entry['run_id']}` | `{entry['sha256'][:16]}…` | {entry['why']} |"
        )

    lines.extend(
        [
            "",
            "Every path above is committed; the generator refuses to cite a receipt that is "
            "not. Generation arms are additionally checked against the shipped prompt hash, "
            "so ADR-0019's rejected candidate cannot enter this comparison even though its "
            "receipt sits in `reports/` under a `phase18_` prefix with better abstention "
            "numbers than the cell that ships.",
        ]
    )

    receipt = {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "config_hash": current_config_hash,
        "golden_set_hash": expected_golden_hash,
        "numeric_epsilon": cfg.thresholds.numeric_epsilon,
        "product_prompt_sha256": PROMPT_SHA256,
        "retrieval_scored_rows": scored_rows,
        "golden_examples": len(examples),
        "populations": {
            population.key: [arm.label for arm in population.arms]
            for population in GENERATION_POPULATIONS
        },
        "sources": sources,
        "rejected_run_ids": [REJECTED_CANDIDATE_RUN_ID],
    }
    return "\n".join(lines) + "\n", receipt


def run_variant_matrix(args: Namespace) -> int:
    report_path = Path(args.report)
    receipt_path = Path(args.receipt)
    text, receipt = build_report(golden_path=Path(args.golden))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"variant matrix: {report_path}")
    print(f"receipt: {receipt_path}")
    return 0


__all__ = [
    "GENERATION_POPULATIONS",
    "RETRIEVAL_ARMS",
    "GenerationArm",
    "Population",
    "RetrievalArm",
    "build_report",
    "reproduction_count",
    "run_variant_matrix",
    "score_arm",
]
