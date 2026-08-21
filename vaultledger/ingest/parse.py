"""PDF parsing (SPEC.md Section 9 step 1).

``pdfplumber`` extracts per-page text plus word geometry. Every page's text is
tracked with global character offsets into the document's ``full_text`` so
chunks (and therefore citations) can point at exact spans. Word geometry is
kept because some layouts encode meaning in position — e.g. statement layout A
distinguishes debit from credit purely by which column an amount sits in,
which flat text extraction destroys.

Pages with (near-)zero extractable text are flagged rather than crashed on;
the OCR fallback is a stretch goal (SPEC FR1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from vaultledger.schemas import Corpus


@dataclass
class Word:
    """One extracted word with its horizontal extent (PDF points)."""

    text: str
    x0: float
    x1: float
    top: float


@dataclass
class ParsedPage:
    page_number: int  # 1-based
    text: str
    char_start: int  # offset of this page's text within full_text
    char_end: int
    words: list[Word] = field(default_factory=list)


@dataclass
class ParsedDoc:
    doc_id: str
    source_filename: str
    page_count: int
    full_text: str  # page texts joined with "\n"
    pages: list[ParsedPage]
    needs_ocr: bool = False  # some page had ~no extractable text
    ocr_pages: tuple[int, ...] = ()  # pages whose text layer came from OCR preprocessing
    corpus: Corpus = "synthetic"


# Rows are grouped by their `top` coordinate; words whose tops differ by less
# than this many points belong to the same visual row.
_ROW_TOLERANCE = 3.0

#: A page with fewer than this many non-whitespace characters is treated as having
#: no usable text layer. ADR-0012's provenance guarantee depends on `ocr.py` using
#: this same threshold to decide which pages it OCR'd: if the two ever disagree, a
#: page could be OCR'd without being marked `ocr_derived`, which no downstream check
#: would catch. Import it — do not restate the literal.
MIN_PAGE_TEXT_CHARS = 20


def rows_from_words(words: list[Word]) -> list[list[Word]]:
    """Group a page's words into visual rows, top-to-bottom, left-to-right."""
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if rows and abs(rows[-1][0].top - w.top) < _ROW_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w.x0) for r in rows]


def parse_pdf(path: str | Path) -> ParsedDoc:
    """Extract text + word geometry from one PDF, with exact global offsets."""
    path = Path(path)
    pages: list[ParsedPage] = []
    texts: list[str] = []
    needs_ocr = False
    offset = 0

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len(text.strip()) < MIN_PAGE_TEXT_CHARS:
                needs_ocr = True
            words = [
                Word(text=w["text"], x0=w["x0"], x1=w["x1"], top=w["top"])
                for w in page.extract_words()
            ]
            pages.append(
                ParsedPage(
                    page_number=i,
                    text=text,
                    char_start=offset,
                    char_end=offset + len(text),
                    words=words,
                )
            )
            texts.append(text)
            offset += len(text) + 1  # +1 for the joining "\n"

    return ParsedDoc(
        doc_id=path.stem,
        source_filename=path.name,
        page_count=len(pages),
        full_text="\n".join(texts),
        pages=pages,
        needs_ocr=needs_ocr,
    )


__all__ = ["Word", "ParsedPage", "ParsedDoc", "parse_pdf", "rows_from_words"]
