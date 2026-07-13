"""Chunking (SPEC.md Section 8.4 / Section 9 step 4).

Line-packing chunker: whole lines are packed into chunks up to a character
budget with ~15% overlap. Splitting on line boundaries guarantees a
transaction row is never cut in half (SPEC 8.4) — in these documents every
transaction, deduction, and line item is exactly one rendered line.

Chunks never cross a page boundary, so page attribution is exact, and every
chunk's text is a literal slice ``full_text[char_start:char_end]`` — that
identity is what makes citations exact, and Phase 2's tests assert it for
every chunk in the corpus.

Budgets are in characters (~4 chars/token heuristic): 2400 chars ≈ 600 tokens,
inside SPEC's 500–800-token target.
"""

from __future__ import annotations

from vaultledger.schemas import Chunk

from .parse import ParsedDoc

DEFAULT_MAX_CHARS = 2400
DEFAULT_OVERLAP_FRAC = 0.15


def chunk_doc(
    doc: ParsedDoc,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_frac: float = DEFAULT_OVERLAP_FRAC,
) -> list[Chunk]:
    """Split one parsed document into overlapping, line-aligned chunks."""
    chunks: list[Chunk] = []

    for page in doc.pages:
        if not page.text:
            continue
        # (global_start, global_end) for each line on the page; the +1 offsets
        # account for the "\n" separators inside the page text.
        lines: list[tuple[int, int]] = []
        pos = page.char_start
        for line in page.text.split("\n"):
            lines.append((pos, pos + len(line)))
            pos += len(line) + 1

        i = 0
        while i < len(lines):
            start = lines[i][0]
            j = i
            while j + 1 < len(lines) and lines[j + 1][1] - start <= max_chars:
                j += 1
            end = lines[j][1]
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#c{len(chunks)}",
                    doc_id=doc.doc_id,
                    text=doc.full_text[start:end],
                    page=page.page_number,
                    char_start=start,
                    char_end=end,
                )
            )
            if j + 1 >= len(lines):
                break
            # Step back so ~overlap_frac of the chunk repeats, but always
            # advance by at least one line (bounded loop, SPEC 15.2).
            overlap_start = end - int(max_chars * overlap_frac)
            k = j + 1
            while k > i + 1 and lines[k - 1][0] >= overlap_start:
                k -= 1
            i = k

    return chunks


__all__ = ["chunk_doc", "DEFAULT_MAX_CHARS", "DEFAULT_OVERLAP_FRAC"]
