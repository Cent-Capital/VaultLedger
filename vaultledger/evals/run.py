"""CLI runner for Phase 3 evals and manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vaultledger.config import CONFIG_PATH, Config, load_config
from vaultledger.evals.golden import (
    DEFAULT_GOLDEN_PATH,
    golden_hash,
    load_golden_set,
    validate_expected_snippets,
)
from vaultledger.evals.metrics import retrieval_metrics
from vaultledger.generate import OllamaGenerator, answer_question
from vaultledger.index.embed import OllamaEmbedder
from vaultledger.ingest.pipeline import load_chunks
from vaultledger.retrieve import NaiveDenseRetriever
from vaultledger.schemas import RunManifest


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _config_hash() -> str:
    return hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()


def _chunks_by_doc(index_dir: Path) -> dict[str, str]:
    chunks = load_chunks(index_dir)
    return {c.doc_id: c.text for c in chunks}


def _ensure_phase3_inputs(cfg: Config) -> None:
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    required = [index_dir / "chunks.jsonl", index_dir / "chroma", index_dir / "records.db"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "missing Phase 2 index artifacts; run `make data && make ingest` first: "
            + ", ".join(missing)
        )


def validate_golden(args: argparse.Namespace) -> int:
    cfg = load_config()
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    _ensure_phase3_inputs(cfg)
    golden = load_golden_set(args.golden)
    errors = validate_expected_snippets(golden.examples, _chunks_by_doc(index_dir))
    if errors:
        for err in errors:
            print(err)
        return 1
    print(
        f"golden set ok: {golden.version}, {len(golden.examples)} examples, "
        f"hash={golden_hash(args.golden)[:12]}"
    )
    return 0


def run_eval(args: argparse.Namespace) -> int:
    cfg = load_config()
    _ensure_phase3_inputs(cfg)
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    golden = load_golden_set(args.golden)

    embedder = OllamaEmbedder(model=cfg.embedding.model, base_url=cfg.embedding.ollama_url)
    if not embedder.is_available():
        msg = (
            f"Ollama embedding model {cfg.embedding.model!r} is unavailable at "
            f"{cfg.embedding.ollama_url}; start Ollama and pull the model."
        )
        if args.skip_if_unavailable:
            print(f"SKIP: {msg}")
            return 0
        raise RuntimeError(msg)

    retriever = NaiveDenseRetriever(index_dir, embedder)
    examples = golden.examples[: args.limit] if args.limit else golden.examples
    ranked_doc_ids: dict[str, list[str]] = {}
    k = args.k
    for ex in examples:
        hits = retriever.retrieve(ex.question, k=k)
        ranked_doc_ids[ex.id] = [h.chunk.doc_id for h in hits]

    metrics, failures = retrieval_metrics(examples, ranked_doc_ids, k=k)
    manifest = RunManifest(
        run_id=f"phase3_{uuid4().hex[:12]}",
        timestamp=datetime.now(UTC).isoformat(),
        git_sha=_git_sha(),
        config_hash=_config_hash(),
        golden_set_hash=golden_hash(args.golden),
        seed=cfg.seed,
        variant="A_naive",
        model=cfg.embedding.model,
        metrics=metrics,
        total_cost_usd=0.0,
        failures=failures,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{manifest.run_id}.json"
    out_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    (out_dir / "phase3_baseline_latest.json").write_text(manifest.model_dump_json(indent=2) + "\n")

    print(json.dumps({"manifest": str(out_path), "metrics": metrics}, indent=2))

    if args.answer_one:
        generator = OllamaGenerator(cfg.models.T1.id, base_url=cfg.embedding.ollama_url)
        if not generator.is_available():
            print(f"SKIP answer_one: generation model {cfg.models.T1.id!r} unavailable")
            return 0
        answer_examples = examples
        if args.answer_id:
            answer_examples = [ex for ex in golden.examples if ex.id == args.answer_id]
            if not answer_examples:
                raise ValueError(f"unknown golden example id: {args.answer_id}")
        ex = answer_examples[0]
        answer = answer_question(
            ex.question,
            retriever,
            generator,
            model_id=cfg.models.T1.id,
            k=k,
        )
        answer_path = out_dir / f"{manifest.run_id}_answer.json"
        cited_doc_ids = {c.doc_id for c in answer.citations}
        expected_doc_ids = set(ex.expected_doc_ids)
        payload = {
            "example_id": ex.id,
            "question": ex.question,
            "expected_answer": ex.expected_answer,
            "expected_doc_ids": ex.expected_doc_ids,
            "citation_docs_match_expected": bool(expected_doc_ids & cited_doc_ids),
            "answer": answer.model_dump(),
        }
        answer_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"answer_one: {answer_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m vaultledger.evals")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate golden-set anchors against chunks")
    validate.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    validate.set_defaults(func=validate_golden)

    run = sub.add_parser("run", help="Run the Phase 3 dense retrieval baseline")
    run.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    run.add_argument("--variant", default="A_naive", choices=["A_naive"])
    run.add_argument("--k", type=int, default=20)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--out-dir", default="reports")
    run.add_argument("--skip-if-unavailable", action="store_true")
    run.add_argument("--answer-one", action="store_true")
    run.add_argument("--answer-id", default="")
    run.set_defaults(func=run_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


__all__ = ["main"]
