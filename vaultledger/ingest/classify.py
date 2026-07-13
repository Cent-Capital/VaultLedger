"""Document-type classification (SPEC.md Section 9 step 2).

SPEC allows "few-shot local LLM or keyword heuristic". The heuristic is chosen
first (deviation logged in PROGRESS.md): it is deterministic, free, and — on a
synthetic corpus whose ground truth we hold — directly scoreable. If a future
corpus breaks it, the LLM classifier becomes a measured upgrade, not a default.

Match order matters: "1099" is the most specific marker; pay stubs and bank
statements both contain the word "statement", so their distinctive headers are
checked before the generic invoice fallback.
"""

from __future__ import annotations

from vaultledger.schemas import DocType


def classify_doc_type(text: str) -> DocType:
    """Classify a document from its extracted text (first page is enough)."""
    head = "\n".join(text.splitlines()[:8]).lower()

    if "1099-nec" in head or "form 1099" in head:
        return "form_1099"
    if "earnings statement" in head or "pay statement" in head:
        return "pay_stub"
    if "account statement" in head or "monthly account statement" in head:
        return "bank_statement"
    if "invoice" in head:
        return "invoice"
    return "unknown"


__all__ = ["classify_doc_type"]
