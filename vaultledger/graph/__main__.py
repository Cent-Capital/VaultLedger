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
from .quality import score_graph, score_graph_with_account_aliases


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
    export.add_argument("--replace", action="store_true")
    extracted_export = subparsers.add_parser("export-extracted")
    extracted_export.add_argument(
        "--graphml",
        default="data/graph/lightrag/graph_chunk_entity_relation.graphml",
    )
    extracted_export.add_argument("--output", default=None)
    extracted_export.add_argument("--replace", action="store_true")
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
            replace=args.replace,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "export-extracted":
        extracted = load_lightrag_graphml(cfg.repo_path(args.graphml))
        result = export_obsidian_vault(
            extracted,
            document_ids=_document_ids(ground_truth_dir),
            output_dir=cfg.repo_path(args.output or cfg.graph.obsidian_dir),
            replace=args.replace,
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
    strict = score_graph(extracted, expected)
    alias = score_graph_with_account_aliases(extracted, expected)
    print(
        json.dumps(
            {"strict": strict.as_metrics(), "account_alias": alias.as_metrics()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
