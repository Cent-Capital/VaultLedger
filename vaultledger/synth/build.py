"""Build the synthetic corpus: seed -> records -> PDFs + ground-truth JSON +
entities.json (SPEC.md Phase 1).

Output layout under ``data/``:
    synthetic_pdfs/<doc_id>.pdf        rendered document (gitignored; regenerable)
    ground_truth/<doc_id>.json         typed record + entities + defect markers
    ground_truth/entities.json         intended entity/relation graph

The build clears prior generated files first so the directory contents are a
pure function of the seed — no leftover doc from an earlier run can pollute a
regeneration. PDFs are gitignored (byte-identical from the seed, so committing
binaries buys nothing); the ground-truth JSON is committed as the scoreable
source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import REPO_ROOT, load_config
from .records import build_entities, generate_records
from .render import render_pdf

DATA_DIR = REPO_ROOT / "data"


def _write_json(path: Path, obj: dict) -> None:
    # sort_keys + fixed indent + trailing newline -> byte-stable across runs.
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _clear_generated(pdf_dir: Path, gt_dir: Path) -> None:
    for p in pdf_dir.glob("*.pdf"):
        p.unlink()
    for p in gt_dir.glob("*.json"):
        p.unlink()


def build(out_dir: Path | str = DATA_DIR, seed: int | None = None) -> dict:
    """Generate the whole corpus under ``out_dir``. Returns a summary dict."""
    out_dir = Path(out_dir)
    if seed is None:
        seed = load_config().seed

    pdf_dir = out_dir / "synthetic_pdfs"
    gt_dir = out_dir / "ground_truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    _clear_generated(pdf_dir, gt_dir)

    docs = generate_records(seed)

    for doc in docs:
        (pdf_dir / f"{doc.doc_id}.pdf").write_bytes(render_pdf(doc))
        _write_json(
            gt_dir / f"{doc.doc_id}.json",
            {
                "doc_id": doc.doc_id,
                "doc_type": doc.doc_type,
                "layout": doc.layout,
                "record": doc.record,
                "entities": doc.entities,
                "defects": doc.defects,
                "pii_entity_types": doc.pii_entity_types,
                "has_adversarial_note": doc.adversarial_note is not None,
            },
        )

    entities = build_entities(seed, docs)
    _write_json(gt_dir / "entities.json", entities)

    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc.doc_type] = counts.get(doc.doc_type, 0) + 1

    return {
        "seed": seed,
        "out_dir": str(out_dir),
        "total_docs": len(docs),
        "counts_by_type": counts,
        "doc_ids": [d.doc_id for d in docs],
        "hard_cases": entities["hard_cases"],
    }


def main() -> None:
    summary = build()
    print(f"Synthetic corpus built from seed={summary['seed']} -> {summary['out_dir']}")
    print(f"  total docs: {summary['total_docs']}")
    for doc_type, n in sorted(summary["counts_by_type"].items()):
        print(f"    {doc_type:16s} {n}")
    hc = summary["hard_cases"]
    print(f"  injection docs:     {hc['injection_docs']}")
    print(f"  wrong-total docs:   {hc['wrong_total_docs']}")
    print(f"  near-duplicate:     {hc['near_duplicate_docs']}")


if __name__ == "__main__":
    main()
