"""Phase-15 deterministic graph tooling."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from vaultledger.config import load_config

from .ground_truth import load_ground_truth
from .index import build_lightrag_index, write_index_receipt
from .lightrag_io import load_lightrag_graphml
from .obsidian import export_obsidian_vault
from .quality import score_graph


def _document_ids(ground_truth_dir: Path) -> list[str]:
    return sorted(
        path.stem
        for path in ground_truth_dir.glob("*.json")
        if path.name != "entities.json"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VaultLedger Phase-15 graph tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export-ground-truth")
    export.add_argument("--output", default="exports/obsidian_vault")
    build = subparsers.add_parser("build", help="Build a new LightRAG index and cost receipt")
    build.add_argument("--limit", type=int, default=0, help="0 indexes all documents")
    build.add_argument("--working-dir", help="Override index directory (useful for a smoke run)")
    build.add_argument("--receipt-dir", default="reports")
    score = subparsers.add_parser("score")
    score.add_argument("--graphml", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    ground_truth_dir = cfg.repo_path(cfg.paths.ground_truth)
    expected = load_ground_truth(ground_truth_dir / "entities.json")
    if args.command == "export-ground-truth":
        result = export_obsidian_vault(
            expected,
            document_ids=_document_ids(ground_truth_dir),
            output_dir=cfg.repo_path(args.output),
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "build":
        if args.working_dir:
            cfg = cfg.model_copy(
                update={
                    "graph": cfg.graph.model_copy(update={"working_dir": args.working_dir})
                }
            )
        receipt = asyncio.run(build_lightrag_index(cfg, document_limit=args.limit))
        receipt_path = write_index_receipt(receipt, cfg.repo_path(args.receipt_dir))
        print(json.dumps({**receipt, "receipt": str(receipt_path)}, indent=2, sort_keys=True))
        return 0
    extracted = load_lightrag_graphml(args.graphml)
    print(json.dumps(score_graph(extracted, expected).as_metrics(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
