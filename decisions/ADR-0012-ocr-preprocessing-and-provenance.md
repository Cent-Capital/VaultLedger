# ADR-0012: OCR by preprocessing, with provenance, because citations cannot detect a misread digit

2026-08-11 · Status: **accepted** (owner decision, Phase 16 scope)

## Context

Phase 16 accepts real user documents (ADR-0011). Real financial documents are frequently
scans or photographs with no extractable text layer, so an ingest path that handles only
text-native PDFs would reject a large share of what users actually own.

The parser already anticipates this. `ingest/parse.py:48` carries a `needs_ocr` flag, set
whenever a page yields near-zero extractable text, and such pages are flagged rather than
crashed on. SPEC FR1 names `pytesseract` + `pdf2image` as a stretch-goal fallback.
Detection exists; execution does not.

**The reason this needs a decision record rather than a ticket** is that OCR breaks an
assumption every safety mechanism in this system rests on: that the extracted text
faithfully represents the document.

The citation verifier at `generate/reliable.py:229-233` checks that a normalized snippet
is a **substring of the chunk text**. It verifies fidelity to the chunk, not fidelity to
the source document — it has no access to the original pixels. If OCR writes `$1,284.50`
where the paper says `$1,234.50`, the chunk contains the wrong figure, the model quotes
it word-for-word, the verifier passes, and the user receives a confidently wrong number
with a citation that is technically valid. Guardrails do not catch it either; nothing in
the pipeline is comparing text against the image.

OCR is weakest precisely on digits, and digits are what this product exists to answer
questions about.

## Options

**Defer OCR; fail clearly.** Keep text-native PDFs only and return an explicit "this
document could not be read" message for scans. Adds no dependency and no silent-failure
mode. Rejected as the v1 default because it excludes a large fraction of genuine user
documents, though it remains the correct behaviour if OCR is unavailable at runtime.

**In-parser OCR with geometry reconstruction.** The route SPEC FR1 names: run
`pytesseract` inside the parser and rebuild the `Word` geometry the current code depends
on. Costs several days, because per-word bounding boxes must be reconstructed and
reconciled with the existing character-offset model — and it carries exactly the same
digit-misreading risk as the cheaper option. Rejected: the additional effort buys
geometry fidelity, not correctness.

**Preprocessing with `ocrmypdf --skip-text`.** Add an invisible text layer to scanned
pages only, before ingest, then let the existing `pdfplumber` path run unchanged. Page
offsets, chunking, citation spans, and every downstream contract are untouched, because
by the time VaultLedger sees the file it is an ordinary text-layer PDF.

## Decision

Use **`ocrmypdf --skip-text` as a preprocessing step**, gated on the existing `needs_ocr`
flag. `--skip-text` is required, not optional: it leaves pages that already have a text
layer alone, so a mixed document is never re-OCR'd over good text.

Three obligations travel with it, and none is optional:

1. **OCR-derived documents carry a provenance flag** through ingest, and any answer
   citing an OCR'd page is **visibly marked in the UI** as drawn from a scanned document.
   The user, not the verifier, is the last line of defence here, and they can only act on
   information they are shown.
2. **OCR'd pages never enter an eval population.** Every committed metric keeps its
   synthetic-corpus denominator (ADR-0011). A recall or citation number computed partly
   over OCR'd text would describe a corpus for which no ground truth exists.
3. **If `ocrmypdf` or Tesseract is unavailable at runtime, fall back to failing clearly**
   — the rejected first option becomes the degraded path, never a silent skip that leaves
   a scanned document indexed as empty.

## Consequences

**The silent-failure mode is mitigated, not eliminated.** A flagged wrong figure is still
a wrong figure. This decision makes the risk visible and attributable rather than hidden;
it does not make OCR accurate. Any product claim about answer correctness must therefore
be scoped to text-native documents until an OCR-specific evaluation exists.

**Statement parsing may degrade on scans.** The parser keeps word geometry because some
layouts encode meaning in position — statement layout A distinguishes debit from credit
purely by which column an amount sits in. OCR geometry is approximate, so scanned
statements of that layout may misclassify transaction direction. This is a distinct
failure from digit misreading and is not addressed by the provenance flag.

**A second install dependency appears.** Tesseract must be present on the user's machine.
Whether that is acceptable for a non-technical recipient, or whether OCR should be
owner's-machine-only for v1, is an open Phase-17 packaging question and is deliberately
not settled here.

**Mitigations considered and deferred**, recorded so they are not re-discovered as novel:
Tesseract per-word confidence scores could flag low-confidence numerals; dual-engine
agreement (Tesseract plus macOS Vision) could catch disagreement on digits; a
"verify these figures against your document" affordance could put review in front of the
user for numeric answers. All three are real options. None is in Phase 16 scope, and the
residual risk is accepted knowingly rather than by omission.

## Evidence

- `ingest/parse.py:48` — `needs_ocr: bool` flag already set on near-zero-text pages.
- `generate/reliable.py:229-233` — citation verification is a normalized-substring check
  against the chunk, with no reference to the source image.
- `ingest/parse.py` module docstring — word geometry is retained specifically because
  statement layout A encodes debit versus credit by column position.
- SPEC FR1 and SPEC §9 step 1 — OCR named as a stretch fallback via `pytesseract` +
  `pdf2image`; this ADR deviates from that named implementation while keeping the goal.
- SPEC §19 edge-case list already requires "image-only PDF (OCR path or graceful
  'couldn't read')" to be covered as a test.
