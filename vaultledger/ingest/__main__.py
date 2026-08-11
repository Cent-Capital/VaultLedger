"""CLI: ``python -m vaultledger.ingest [--no-embed]`` (also ``make ingest``)."""

from __future__ import annotations

import argparse
import json
import sys

from vaultledger.config import load_config

from .pipeline import run_ingest
from .watcher import InboxWatcher


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the PDF corpus and build indexes.")
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="skip the vector index (no Ollama needed); SQLite + chunks + BM25 still build",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live-once",
        action="store_true",
        help="scan the external live inbox through its stability window, then exit",
    )
    mode.add_argument(
        "--watch",
        action="store_true",
        help="watch the external live inbox for a finite configured poll budget",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="skip incremental LightRAG insertion for live-document modes",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="override the bounded watcher poll count",
    )
    args = parser.parse_args()

    if args.live_once or args.watch:
        cfg = load_config()
        watcher = InboxWatcher(
            cfg,
            embed=not args.no_embed,
            graph=not args.no_graph,
        )
        polls = (
            args.max_polls
            if args.max_polls is not None
            else (
                cfg.live.watcher_max_polls
                if args.watch
                else cfg.live.watcher_stable_polls
            )
        )
        results = watcher.watch(max_polls=polls)
        for result in results:
            print(json.dumps(result.as_receipt(), sort_keys=True))
        failed = [result for result in results if result.status != "ok"]
        return 1 if failed else 0

    result = run_ingest(embed=not args.no_embed)
    print(
        f"ingested {result.docs_ok} docs ({result.docs_failed} failed), "
        f"{result.chunks} chunks, vector index {'built' if result.embedded else 'SKIPPED'}"
    )
    for failure in result.failures:
        print(f"  FAILED: {failure}", file=sys.stderr)
    return 1 if result.docs_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
