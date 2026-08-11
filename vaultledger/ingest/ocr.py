"""Phase 16 OCR preprocessing with page-level provenance (ADR-0012).

The existing parser remains the only source of offsets and word geometry. This
module first probes the original PDF, invokes ``ocrmypdf --skip-text`` only when
the probe flags a page, and reparses the resulting ordinary text-layer PDF.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from .parse import MIN_PAGE_TEXT_CHARS, ParsedDoc, parse_pdf


class OcrUnavailableError(RuntimeError):
    """Required local OCR executables are not installed."""


class OcrProcessingError(RuntimeError):
    """OCR ran but did not produce a readable text-layer PDF."""


@dataclass(frozen=True)
class OcrResult:
    parsed: ParsedDoc
    processed_path: Path
    ocr_pages: tuple[int, ...]

    @property
    def ocr_derived(self) -> bool:
        return bool(self.ocr_pages)


def prepare_pdf(
    path: str | Path,
    *,
    output_dir: str | Path,
    timeout_seconds: float,
    parser: Callable[[str | Path], ParsedDoc] = parse_pdf,
    executable: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> OcrResult:
    """Return a user-corpus parsed PDF, preprocessing scanned pages if needed.

    A missing executable, non-zero OCR exit, timeout, missing output, or still
    unreadable page is an explicit error. None of those paths may yield chunks.
    """
    source = Path(path).resolve()
    initial = parser(source)
    ocr_pages = tuple(
        page.page_number
        for page in initial.pages
        if len(page.text.strip()) < MIN_PAGE_TEXT_CHARS
    )
    if not ocr_pages:
        return OcrResult(
            parsed=replace(initial, corpus="user"),
            processed_path=source,
            ocr_pages=(),
        )

    missing = [name for name in ("ocrmypdf", "tesseract") if executable(name) is None]
    if missing:
        raise OcrUnavailableError(
            "scanned PDF needs OCR, but these local tools are unavailable: "
            + ", ".join(missing)
        )

    target_dir = Path(output_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / f"{source.stem}.ocr.pdf"
    temp_path = target_dir / f".{source.stem}.{uuid4().hex}.ocr.pdf"
    command = [
        "ocrmypdf",
        "--skip-text",
        "--output-type",
        "pdf",
        str(source),
        str(temp_path),
    ]
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        temp_path.unlink(missing_ok=True)
        raise OcrProcessingError(
            f"OCR exceeded the {timeout_seconds:g}s per-file timeout"
        ) from exc
    if completed.returncode != 0:
        temp_path.unlink(missing_ok=True)
        details = (completed.stderr or completed.stdout or "no diagnostic output").strip()
        raise OcrProcessingError(f"ocrmypdf failed with exit {completed.returncode}: {details}")
    if not temp_path.is_file():
        raise OcrProcessingError("ocrmypdf reported success but produced no output PDF")

    try:
        processed = parser(temp_path)
        if processed.needs_ocr:
            raise OcrProcessingError(
                "OCR completed, but at least one scanned page still has no readable text"
            )
        temp_path.replace(final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    parsed = replace(
        processed,
        doc_id=source.stem,
        source_filename=source.name,
        ocr_pages=ocr_pages,
        corpus="user",
    )
    return OcrResult(parsed=parsed, processed_path=final_path, ocr_pages=ocr_pages)


__all__ = [
    "OcrProcessingError",
    "OcrResult",
    "OcrUnavailableError",
    "prepare_pdf",
]
