"""CLI: ``python -m vaultledger.ingest [--no-embed]`` (also ``make ingest``)."""

from __future__ import annotations

import argparse
import sys

from .pipeline import run_ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the PDF corpus and build indexes.")
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="skip the vector index (no Ollama needed); SQLite + chunks + BM25 still build",
    )
    args = parser.parse_args()

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
