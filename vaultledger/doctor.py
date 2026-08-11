"""Read-only readiness checks for the Track-A local workflow.

The doctor intentionally does not install, download, generate, or ingest
anything. It tells a fresh user which documented setup step is still missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from vaultledger import __version__, load_config
from vaultledger.config import REPO_ROOT

EXPECTED_PDFS = 60
REQUIRED_IMPORTS = (
    "chromadb",
    "pdfplumber",
    "presidio_analyzer",
    "rank_bm25",
    "sentence_transformers",
    "streamlit",
)


@dataclass(frozen=True)
class Check:
    """One actionable readiness result."""

    name: str
    passed: bool
    detail: str
    remedy: str = ""
    required: bool = True


def _tool_version(executable: str, *args: str) -> str:
    """Return a bounded one-line version for a discovered local executable."""

    try:
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "version unavailable"
    output = result.stdout.strip() or result.stderr.strip()
    return output.splitlines()[0] if output else "version unavailable"


def _ocr_check() -> Check:
    """Describe optional scan support without making text-PDF readiness fail."""

    ocrmypdf = shutil.which("ocrmypdf")
    tesseract = shutil.which("tesseract")
    missing = [
        name
        for name, path in (("ocrmypdf", ocrmypdf), ("tesseract", tesseract))
        if not path
    ]
    if missing:
        return Check(
            "Scanned-PDF support",
            False,
            f"optional OCR tools missing: {', '.join(missing)}; text PDFs still work",
            "Install Homebrew, then run `brew install ocrmypdf` for scanned PDFs.",
            required=False,
        )
    return Check(
        "Scanned-PDF support",
        True,
        f"{_tool_version(ocrmypdf, '--version')}; "
        f"{_tool_version(tesseract, '--version')}",
        required=False,
    )


def _model_names(base_url: str) -> set[str]:
    """Return Ollama model names from the local tags endpoint."""

    endpoint = f"{base_url.rstrip('/')}/api/tags"
    with urlopen(endpoint, timeout=2) as response:  # noqa: S310 - configured loopback endpoint
        payload = json.loads(response.read())
    return {str(model["name"]) for model in payload.get("models", [])}


def _has_model(names: set[str], wanted: str) -> bool:
    wanted = wanted.removeprefix("ollama/")
    return wanted in names or f"{wanted}:latest" in names


def run_checks(repo_root: Path | None = None) -> list[Check]:
    """Run non-mutating setup checks in documented workflow order."""

    cfg = load_config()
    root = repo_root or REPO_ROOT
    pdf_dir = root / cfg.paths.pdfs
    index_dir = root / cfg.paths.index_dir
    reports_dir = root / "reports"

    checks = [
        Check(
            "Python",
            sys.version_info >= (3, 11),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "Install Python 3.11 or newer.",
        ),
        Check("Config", True, f"loaded config.yaml; VaultLedger {__version__}"),
    ]

    missing_imports = [name for name in REQUIRED_IMPORTS if importlib.util.find_spec(name) is None]
    checks.append(
        Check(
            "Dependencies",
            not missing_imports,
            "all required packages importable"
            if not missing_imports
            else f"missing: {', '.join(missing_imports)}",
            "Run `make install`.",
        )
    )
    checks.append(_ocr_check())

    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
    checks.append(
        Check(
            "Synthetic corpus",
            pdf_count == EXPECTED_PDFS,
            f"{pdf_count}/{EXPECTED_PDFS} PDFs",
            "Run `make data`.",
        )
    )

    required_index_files = (
        index_dir / "records.db",
        index_dir / "chunks.jsonl",
        index_dir / "bm25.json",
    )
    missing_index = [path.name for path in required_index_files if not path.exists()]
    chroma_ready = (index_dir / "chroma").exists()
    checks.append(
        Check(
            "Local indexes",
            not missing_index and chroma_ready,
            "SQLite, chunks, BM25, and Chroma present"
            if not missing_index and chroma_ready
            else f"missing: {', '.join(missing_index + ([] if chroma_ready else ['chroma/']))}",
            "Start Ollama, then run `make ingest`.",
        )
    )

    try:
        names = _model_names(cfg.embedding.ollama_url)
        required_models = (cfg.embedding.model, cfg.models.T1.id)
        missing_models = [model for model in required_models if not _has_model(names, model)]
        checks.append(
            Check(
                "Ollama models",
                not missing_models,
                "embedding and generation models available"
                if not missing_models
                else f"missing: {', '.join(missing_models)}",
                "Run `ollama pull nomic-embed-text` and `ollama pull qwen3:8b`.",
            )
        )
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        checks.append(
            Check(
                "Ollama models",
                False,
                f"local Ollama unavailable: {exc}",
                "Start Ollama, then pull the two README models.",
            )
        )

    required_reports = (
        reports_dir / "phase4_latest.json",
        reports_dir / "phase7_latest.json",
        reports_dir / "phase9_judge_latest.json",
        reports_dir / "regression_latest.json",
    )
    missing_reports = [path.name for path in required_reports if not path.exists()]
    checks.append(
        Check(
            "Track-A receipts",
            not missing_reports,
            "retrieval, safety, judge, and regression artifacts present"
            if not missing_reports
            else f"missing: {', '.join(missing_reports)}",
            "Run `make eval-full` after setup.",
        )
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check VaultLedger Track-A readiness.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    args = parser.parse_args(argv)

    checks = run_checks()
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        for check in checks:
            mark = "PASS" if check.passed else ("FAIL" if check.required else "WARN")
            print(f"[{mark}] {check.name}: {check.detail}")
            if not check.passed and check.remedy:
                print(f"       Next: {check.remedy}")
        required = [check for check in checks if check.required]
        optional = [check for check in checks if not check.required]
        optional_ready = sum(check.passed for check in optional)
        print(
            f"\n{sum(check.passed for check in required)}/{len(required)} required checks passed; "
            f"{optional_ready}/{len(optional)} optional capabilities ready."
        )
    return 0 if all(check.passed for check in checks if check.required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
