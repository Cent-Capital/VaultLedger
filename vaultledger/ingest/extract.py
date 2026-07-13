"""Field extraction: rendered text -> typed records (SPEC.md Section 9 step 2).

Extraction reads only what the ingestion parser recovered from the PDF —
never the ground-truth JSON, which stays quarantined for scoring. Each of the
four document types has two visual layouts (Phase 1 requirement); the
extractor detects the layout from its header markers and parses accordingly.

The one genuinely positional case: statement layout A prints debit and credit
as separate right-aligned columns, and flat text extraction collapses them
into a single amount per line. The extractor therefore classifies each
amount by its horizontal position on the page (a word ending left of the
column boundary is a debit, right of it a credit).

Extraction failures raise ``ExtractionError``; the pipeline records the doc
as failed and moves on — one bad document never aborts an ingest run
(SPEC FR11 "never crash on one bad doc").
"""

from __future__ import annotations

import re
from datetime import date

from vaultledger.schemas import DocType

from .parse import ParsedDoc, rows_from_words
from .records import (
    ExtractedRecord,
    Form1099Record,
    InvoiceRecord,
    LineItem,
    PayStubRecord,
    StatementRecord,
    Transaction,
)

_MONEY = r"\$(-?[\d,]+\.\d{2})"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Statement layout A column geometry (renderer: 10mm margin; cells 28/94/34/34mm).
# The debit column's right edge sits at 166mm = ~470pt; the credit column's at
# 200mm = ~567pt. An amount word ending left of the midpoint is a debit.
_DEBIT_CREDIT_BOUNDARY_PT = 520.0


class ExtractionError(ValueError):
    """Raised when a document's text does not match any known layout."""


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def _search(pattern: str, text: str, doc_id: str) -> re.Match:
    m = re.search(pattern, text, flags=re.MULTILINE)
    if not m:
        raise ExtractionError(f"{doc_id}: pattern not found: {pattern!r}")
    return m


# --- Bank statement ---------------------------------------------------------


def _extract_statement(doc: ParsedDoc) -> StatementRecord:
    text = doc.full_text
    lines = text.splitlines()

    if "NORTHWIND BANK" in lines[0]:  # layout A: positional debit/credit columns
        holder = lines[2]
        m = _search(r"^Account: \*\*\*\*(\d{4}) \((\w+)\)$", text, doc.doc_id)
        last4, acct_type = m.group(1), m.group(2).lower()
        p = _search(r"^Statement period: (\S+) to (\S+)$", text, doc.doc_id)
        opening = _money(_search(rf"^Opening balance: {_MONEY}$", text, doc.doc_id).group(1))
        closing = _money(_search(rf"^Closing balance: {_MONEY}$", text, doc.doc_id).group(1))

        transactions: list[Transaction] = []
        for page in doc.pages:
            for row in rows_from_words(page.words):
                if len(row) < 3 or not _DATE.match(row[0].text):
                    continue
                amount_word = row[-1]
                m_amt = re.fullmatch(_MONEY, amount_word.text)
                if not m_amt:
                    continue
                txn_type = "debit" if amount_word.x1 < _DEBIT_CREDIT_BOUNDARY_PT else "credit"
                transactions.append(
                    Transaction(
                        date=date.fromisoformat(row[0].text),
                        description=" ".join(w.text for w in row[1:-1]),
                        amount=_money(m_amt.group(1)),
                        type=txn_type,
                    )
                )
    elif "Cascade Credit Union" in lines[0]:  # layout B: signed single amount column
        holder = _search(r"^Member: (.+)$", text, doc.doc_id).group(1)
        m = _search(r"^Account no\. \*\*\*\*(\d{4}) \| Type: (\w+)$", text, doc.doc_id)
        last4, acct_type = m.group(1), m.group(2).lower()
        p = _search(r"^Period (\S+) - (\S+)$", text, doc.doc_id)
        opening = _money(_search(rf"^Beginning balance {_MONEY}$", text, doc.doc_id).group(1))
        closing = _money(_search(rf"^Ending balance {_MONEY}$", text, doc.doc_id).group(1))

        transactions = []
        for line in lines:
            m_txn = re.fullmatch(rf"(\d{{4}}-\d{{2}}-\d{{2}}) (.+) {_MONEY}", line)
            if m_txn:
                signed = _money(m_txn.group(3))
                transactions.append(
                    Transaction(
                        date=date.fromisoformat(m_txn.group(1)),
                        description=m_txn.group(2),
                        amount=abs(signed),
                        type="credit" if signed > 0 else "debit",
                    )
                )
    else:
        raise ExtractionError(f"{doc.doc_id}: unrecognized bank statement layout")

    return StatementRecord(
        account_holder=holder,
        account_last4=last4,
        account_type=acct_type,
        period_start=date.fromisoformat(p.group(1)),
        period_end=date.fromisoformat(p.group(2)),
        opening_balance=opening,
        closing_balance=closing,
        transactions=transactions,
    )


# --- Pay stub ---------------------------------------------------------------


def _extract_pay_stub(doc: ParsedDoc) -> PayStubRecord:
    text = doc.full_text
    lines = text.splitlines()
    deductions: dict[str, float] = {}

    def _key(name: str) -> str:
        return name.lower().replace(" ", "_")

    if lines[0].startswith("EARNINGS STATEMENT"):  # layout A
        employer = _search(r"^Employer: (.+)$", text, doc.doc_id).group(1)
        employee = _search(r"^Employee: (.+)$", text, doc.doc_id).group(1)
        m = _search(r"^Pay period: (\S+) to (\S+) Pay date: (\S+)$", text, doc.doc_id)
        pay_period, pay_date = f"{m.group(1)} to {m.group(2)}", date.fromisoformat(m.group(3))
        gross = _money(_search(rf"^Gross pay: {_MONEY}$", text, doc.doc_id).group(1))
        net = _money(_search(rf"^Net pay: {_MONEY}$", text, doc.doc_id).group(1))
        in_table = False
        for line in lines:
            if line == "Deduction Amount":
                in_table = True
                continue
            if line.startswith("Net pay:"):
                break
            if in_table:
                m_d = re.fullmatch(rf"(.+) {_MONEY}", line)
                if m_d:
                    deductions[_key(m_d.group(1))] = _money(m_d.group(2))
    elif lines[0].startswith("PAY STATEMENT"):  # layout B
        employer = lines[1]
        m = _search(r"^Employee: (.+) Pay date: (\S+)$", text, doc.doc_id)
        employee, pay_date = m.group(1), date.fromisoformat(m.group(2))
        p = _search(r"^Period: (\S+) to (\S+)$", text, doc.doc_id)
        pay_period = f"{p.group(1)} to {p.group(2)}"
        gross = _money(_search(rf"^Gross pay {_MONEY}$", text, doc.doc_id).group(1))
        net = _money(_search(rf"^Net pay {_MONEY}$", text, doc.doc_id).group(1))
        for line in lines:
            m_d = re.fullmatch(r"less (.+) -\$([\d,]+\.\d{2})", line)
            if m_d:
                deductions[_key(m_d.group(1))] = _money(m_d.group(2))
    else:
        raise ExtractionError(f"{doc.doc_id}: unrecognized pay stub layout")

    return PayStubRecord(
        employer=employer,
        employee=employee,
        pay_period=pay_period,
        pay_date=pay_date,
        gross_pay=gross,
        net_pay=net,
        deductions=deductions,
    )


# --- Form 1099 ---------------------------------------------------------------


def _extract_1099(doc: ParsedDoc) -> Form1099Record:
    text = doc.full_text
    lines = text.splitlines()

    if lines[0].startswith("Form 1099-NEC"):  # layout A
        year = int(_search(r"^Tax year (\d{4})$", text, doc.doc_id).group(1))
        payer = lines[lines.index("PAYER") + 1]
        recipient = lines[lines.index("RECIPIENT") + 1]
        box1 = _money(
            _search(rf"^Box 1 - Nonemployee compensation {_MONEY}$", text, doc.doc_id).group(1)
        )
    else:  # layout B
        year = int(_search(r"^1099-NEC \((\d{4})\)$", text, doc.doc_id).group(1))
        payer = _search(r"^Payer (.+)$", text, doc.doc_id).group(1)
        recipient = _search(r"^Recipient (.+)$", text, doc.doc_id).group(1)
        box1 = _money(
            _search(rf"^Box 1 Nonemployee compensation: {_MONEY}$", text, doc.doc_id).group(1)
        )

    return Form1099Record(
        payer_name=payer, recipient_name=recipient, tax_year=year, box_amounts={"1": box1}
    )


# --- Invoice ------------------------------------------------------------------


def _extract_invoice(doc: ParsedDoc) -> InvoiceRecord:
    text = doc.full_text
    lines = text.splitlines()
    items: list[LineItem] = []

    if lines[0] == "INVOICE":  # layout A
        number = _search(r"^Invoice #: (\S+)$", text, doc.doc_id).group(1)
        m = _search(r"^Issued: (\S+) Due: (\S+)$", text, doc.doc_id)
        issue_date, due_date = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        vendor = _search(r"^From: (.+)$", text, doc.doc_id).group(1)
        total = _money(_search(rf"^Total {_MONEY}$", text, doc.doc_id).group(1))
        in_table = False
        for line in lines:
            if line == "Description Qty Unit Amount":
                in_table = True
                continue
            if line.startswith("Total "):
                break
            if in_table:
                m_i = re.fullmatch(rf"(.+) (\d+) {_MONEY} {_MONEY}", line)
                if m_i:
                    items.append(
                        LineItem(
                            desc=m_i.group(1),
                            qty=int(m_i.group(2)),
                            unit_price=_money(m_i.group(3)),
                            amount=_money(m_i.group(4)),
                        )
                    )
    elif len(lines) > 1 and lines[1] == "Invoice":  # layout B (vendor name on line 1)
        vendor = lines[0]
        m = _search(r"^Invoice (\S+) Due (\S+)$", text, doc.doc_id)
        number, due_date = m.group(1), date.fromisoformat(m.group(2))
        issue_date = None  # layout B does not print an issue date
        total = _money(_search(rf"^Amount due: {_MONEY}$", text, doc.doc_id).group(1))
        for line in lines:
            m_i = re.fullmatch(rf"(.+) x(\d+) @ {_MONEY} {_MONEY}", line)
            if m_i:
                items.append(
                    LineItem(
                        desc=m_i.group(1),
                        qty=int(m_i.group(2)),
                        unit_price=_money(m_i.group(3)),
                        amount=_money(m_i.group(4)),
                    )
                )
    else:
        raise ExtractionError(f"{doc.doc_id}: unrecognized invoice layout")

    return InvoiceRecord(
        vendor=vendor,
        invoice_number=number,
        issue_date=issue_date,
        due_date=due_date,
        line_items=items,
        total=total,
    )


_EXTRACTORS = {
    "bank_statement": _extract_statement,
    "pay_stub": _extract_pay_stub,
    "form_1099": _extract_1099,
    "invoice": _extract_invoice,
}


def extract_record(doc: ParsedDoc, doc_type: DocType) -> ExtractedRecord:
    """Extract the typed record for a classified document."""
    if doc_type not in _EXTRACTORS:
        raise ExtractionError(f"{doc.doc_id}: no extractor for doc_type={doc_type!r}")
    return _EXTRACTORS[doc_type](doc)


__all__ = ["ExtractionError", "extract_record"]
