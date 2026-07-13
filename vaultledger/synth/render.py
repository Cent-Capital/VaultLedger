"""Render a ``DocRecord`` to a byte-deterministic PDF (SPEC.md 8.3).

Two visual layouts per document type (SPEC requires >= 2) so the ingestion and
parsing paths get exercised against real template variety, not one cloned form.

Byte-determinism (the Phase-1 acceptance criterion) comes from three pins:
- creation date fixed to a constant UTC instant (naive datetimes would pick up
  the host's timezone and diverge between a laptop and CI),
- producer / author / title fixed strings (no library-version drift in bytes),
- core fonts only (no external font files, no embedding nondeterminism).

The renderer never invents financial content — it lays out exactly what
``records.py`` produced, including the deliberately-wrong printed total and the
embedded adversarial line, which must survive into the extracted text.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .records import DocRecord

# A constant instant, timezone-pinned so the emitted /CreationDate is identical
# on every machine. The value itself is arbitrary and clearly synthetic.
_CREATION = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)

_USABLE_W = 190.0  # A4 width (210) minus default 10mm margins each side


def _new_pdf() -> FPDF:
    pdf = FPDF(format="A4")
    pdf.set_creation_date(_CREATION)
    pdf.set_title("VaultLedger synthetic document")
    pdf.set_author("VaultLedger synthetic generator")
    pdf.set_producer("VaultLedger synthetic generator")
    pdf.set_creator("VaultLedger synthetic generator")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    return pdf


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _line(pdf: FPDF, txt: str, h: float = 6, size: float = 10, style: str = "", align: str = "L"):
    pdf.set_font("helvetica", style, size)
    pdf.cell(0, h, text=txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=align)


def _gap(pdf: FPDF, h: float = 3):
    pdf.ln(h)


def _row(pdf: FPDF, cells: list[tuple[float, str, str]], h: float = 6, size: float = 9,
         style: str = "", border: int = 0):
    pdf.set_font("helvetica", style, size)
    for i, (w, text, align) in enumerate(cells):
        last = i == len(cells) - 1
        pdf.cell(
            w,
            h,
            text=text,
            border=border,
            align=align,
            new_x=XPos.LMARGIN if last else XPos.RIGHT,
            new_y=YPos.NEXT if last else YPos.TOP,
        )


# --- Bank statement --------------------------------------------------------


def _render_bank_statement(pdf: FPDF, doc: DocRecord) -> None:
    r = doc.record
    holder_addr = doc.entities.get("holder_address", "")
    masked = f"****{r['account_last4']}"

    if doc.layout == "A":
        _line(pdf, "NORTHWIND BANK", size=16, style="B")
        _line(pdf, "Monthly Account Statement", size=10)
        _gap(pdf)
        _line(pdf, r["account_holder"], size=11, style="B")
        _line(pdf, holder_addr, size=9)
        _line(pdf, f"Account: {masked}  ({r['account_type'].title()})", size=9)
        _line(pdf, f"Statement period: {r['period_start']} to {r['period_end']}", size=9)
        _gap(pdf)
        _row(
            pdf,
            [(28, "Date", "L"), (94, "Description", "L"), (34, "Debit", "R"), (34, "Credit", "R")],
            style="B",
            border="B",
        )
        for t in r["transactions"]:
            debit = _money(t["amount"]) if t["type"] == "debit" else ""
            credit = _money(t["amount"]) if t["type"] == "credit" else ""
            _row(
                pdf,
                [(28, t["date"], "L"), (94, t["description"][:52], "L"),
                 (34, debit, "R"), (34, credit, "R")],
            )
        _gap(pdf)
        _line(pdf, f"Opening balance: {_money(r['opening_balance'])}", size=10)
        _line(pdf, f"Closing balance: {_money(r['closing_balance'])}", size=11, style="B")
    else:
        _line(pdf, "Cascade Credit Union", size=15, style="B", align="C")
        _line(pdf, "Account Statement", size=10, align="C")
        _gap(pdf)
        _line(pdf, f"Member: {r['account_holder']}", size=10, style="B")
        _line(pdf, f"Mailing address: {holder_addr}", size=9)
        _line(pdf, f"Account no. {masked} | Type: {r['account_type'].title()}", size=9)
        _line(pdf, f"Period {r['period_start']} - {r['period_end']}", size=9)
        _gap(pdf)
        _line(pdf, f"Beginning balance {_money(r['opening_balance'])}", size=9)
        _row(pdf, [(30, "Date", "L"), (110, "Description", "L"), (48, "Amount", "R")],
             style="B", border="B")
        for t in r["transactions"]:
            signed = t["amount"] if t["type"] == "credit" else -t["amount"]
            _row(pdf, [(30, t["date"], "L"), (110, t["description"][:60], "L"),
                       (48, _money(signed), "R")])
        _gap(pdf)
        _line(pdf, f"Ending balance {_money(r['closing_balance'])}", size=11, style="B")

    # Embedded adversarial instruction (E4) — carried in the statement body so
    # it lands in extracted text and must be treated as data, never obeyed.
    if doc.adversarial_note:
        _gap(pdf)
        _line(pdf, f"STATEMENT MESSAGE: {doc.adversarial_note}", size=9, style="I")


# --- Pay stub --------------------------------------------------------------


def _render_pay_stub(pdf: FPDF, doc: DocRecord) -> None:
    r = doc.record
    if doc.layout == "A":
        _line(pdf, "EARNINGS STATEMENT", size=16, style="B")
        _gap(pdf)
        _line(pdf, f"Employer: {r['employer']}", size=10, style="B")
        _line(pdf, doc.entities.get("employer_address", ""), size=9)
        _gap(pdf)
        _line(pdf, f"Employee: {r['employee']}", size=10, style="B")
        _line(pdf, doc.entities.get("employee_address", ""), size=9)
        _line(pdf, f"Pay period: {r['pay_period']}   Pay date: {r['pay_date']}", size=9)
        _gap(pdf)
        _line(pdf, f"Gross pay: {_money(r['gross_pay'])}", size=10, style="B")
        _row(pdf, [(120, "Deduction", "L"), (60, "Amount", "R")], style="B", border="B")
        for k, v in r["deductions"].items():
            _row(pdf, [(120, k.replace("_", " ").title(), "L"), (60, _money(v), "R")])
        _gap(pdf)
        _line(pdf, f"Net pay: {_money(r['net_pay'])}", size=12, style="B")
    else:
        _line(pdf, "PAY STATEMENT", size=15, style="B", align="C")
        _line(pdf, r["employer"], size=11, align="C")
        _line(pdf, doc.entities.get("employer_address", ""), size=8, align="C")
        _gap(pdf)
        _row(pdf, [(90, f"Employee: {r['employee']}", "L"),
                   (90, f"Pay date: {r['pay_date']}", "R")], size=10)
        _line(pdf, f"Period: {r['pay_period']}", size=9)
        _gap(pdf)
        _row(pdf, [(90, "Gross pay", "L"), (90, _money(r["gross_pay"]), "R")],
             style="B", border="B")
        for k, v in r["deductions"].items():
            _row(pdf, [(90, f"less {k.replace('_', ' ').title()}", "L"),
                       (90, f"-{_money(v)}", "R")])
        _row(pdf, [(90, "Net pay", "L"), (90, _money(r["net_pay"]), "R")],
             style="B", border="T")


# --- Form 1099 -------------------------------------------------------------


def _render_form_1099(pdf: FPDF, doc: DocRecord) -> None:
    r = doc.record
    box1 = r["box_amounts"].get("1", 0.0)
    if doc.layout == "A":
        _line(pdf, "Form 1099-NEC", size=16, style="B")
        _line(pdf, "Nonemployee Compensation", size=10)
        _line(pdf, f"Tax year {r['tax_year']}", size=10, style="B")
        _gap(pdf)
        _line(pdf, "PAYER", size=10, style="B")
        _line(pdf, r["payer_name"], size=10)
        _line(pdf, doc.entities.get("payer_address", ""), size=9)
        _gap(pdf)
        _line(pdf, "RECIPIENT", size=10, style="B")
        _line(pdf, r["recipient_name"], size=10)
        _line(pdf, doc.entities.get("recipient_address", ""), size=9)
        _gap(pdf)
        _row(pdf, [(120, "Box 1 - Nonemployee compensation", "L"),
                   (60, _money(box1), "R")], style="B", border="B")
    else:
        _line(pdf, f"1099-NEC  ({r['tax_year']})", size=15, style="B", align="C")
        _gap(pdf)
        _row(pdf, [(90, "Payer", "L"), (90, r["payer_name"], "L")], style="B")
        _line(pdf, doc.entities.get("payer_address", ""), size=8)
        _gap(pdf)
        _row(pdf, [(90, "Recipient", "L"), (90, r["recipient_name"], "L")], style="B")
        _line(pdf, doc.entities.get("recipient_address", ""), size=8)
        _gap(pdf)
        _line(pdf, f"Box 1 Nonemployee compensation: {_money(box1)}", size=11, style="B")


# --- Invoice ---------------------------------------------------------------


def _render_invoice(pdf: FPDF, doc: DocRecord) -> None:
    r = doc.record
    printed_total = doc.entities.get("printed_total", r["total"])
    if doc.layout == "A":
        _line(pdf, "INVOICE", size=18, style="B")
        _line(pdf, f"Invoice #: {r['invoice_number']}", size=10)
        _line(pdf, f"Issued: {r['issue_date']}   Due: {r['due_date']}", size=9)
        _gap(pdf)
        _line(pdf, f"From: {r['vendor']}", size=10, style="B")
        _line(pdf, doc.entities.get("issuer_address", ""), size=9)
        _line(pdf, f"Bill To: {doc.entities.get('bill_to', '')}", size=10, style="B")
        _line(pdf, doc.entities.get("bill_to_address", ""), size=9)
        _gap(pdf)
        _row(pdf, [(96, "Description", "L"), (18, "Qty", "R"),
                   (36, "Unit", "R"), (34, "Amount", "R")], style="B", border="B")
        for li in r["line_items"]:
            _row(pdf, [(96, li["desc"][:52], "L"), (18, str(li["qty"]), "R"),
                       (36, _money(li["unit_price"]), "R"), (34, _money(li["amount"]), "R")])
        _gap(pdf)
        _row(pdf, [(150, "Total", "R"), (34, _money(printed_total), "R")],
             style="B", border="T")
    else:
        _line(pdf, f"{r['vendor']}", size=16, style="B", align="C")
        _line(pdf, "Invoice", size=11, align="C")
        _gap(pdf)
        _row(pdf, [(90, f"Invoice {r['invoice_number']}", "L"),
                   (90, f"Due {r['due_date']}", "R")], size=10)
        _line(pdf, f"Billed to: {doc.entities.get('bill_to', '')} "
                   f"({doc.entities.get('bill_to_address', '')})", size=9)
        _gap(pdf)
        for li in r["line_items"]:
            _row(pdf, [(140, f"{li['desc']} x{li['qty']} @ {_money(li['unit_price'])}", "L"),
                       (40, _money(li["amount"]), "R")], size=9)
        _gap(pdf)
        _line(pdf, f"Amount due: {_money(printed_total)}", size=12, style="B", align="R")


_RENDERERS = {
    "bank_statement": _render_bank_statement,
    "pay_stub": _render_pay_stub,
    "form_1099": _render_form_1099,
    "invoice": _render_invoice,
}


def render_pdf(doc: DocRecord) -> bytes:
    """Render one document to PDF bytes, deterministically."""
    pdf = _new_pdf()
    _RENDERERS[doc.doc_type](pdf, doc)
    return bytes(pdf.output())
