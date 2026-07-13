"""Typed extracted-record models (SPEC.md Section 8.2).

These are the extraction-side contracts: what the ingestion pipeline pulls out
of a document's *rendered text* (never from the ground-truth JSON — that stays
reserved for scoring). They mirror SPEC 8.2 exactly, with the two supersets
Phase 1 already established: ``account_type`` on statements (disambiguates one
holder's two accounts) and ``employee``/``pay_date`` on pay stubs (printed on
the document, needed for cross-doc joins later).

Fields a layout simply does not print (e.g. layout-B invoices carry no issue
date) stay ``None`` — extraction reports what the page supports, honestly.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    date: date
    description: str
    amount: float
    type: Literal["debit", "credit"]


class StatementRecord(BaseModel):
    account_holder: str
    account_last4: str
    account_type: str
    period_start: date
    period_end: date
    opening_balance: float
    closing_balance: float
    transactions: list[Transaction] = Field(default_factory=list)


class Form1099Record(BaseModel):
    payer_name: str
    recipient_name: str
    tax_year: int
    box_amounts: dict[str, float] = Field(default_factory=dict)


class LineItem(BaseModel):
    desc: str
    qty: int
    unit_price: float
    amount: float


class InvoiceRecord(BaseModel):
    vendor: str
    invoice_number: str
    issue_date: date | None = None  # layout B does not print it
    due_date: date
    line_items: list[LineItem] = Field(default_factory=list)
    total: float  # the *printed* total (the numeric verifier re-checks it)


class PayStubRecord(BaseModel):
    employer: str
    employee: str
    pay_period: str
    pay_date: date | None = None
    gross_pay: float
    net_pay: float
    deductions: dict[str, float] = Field(default_factory=dict)


ExtractedRecord = StatementRecord | Form1099Record | InvoiceRecord | PayStubRecord

__all__ = [
    "Transaction",
    "StatementRecord",
    "Form1099Record",
    "LineItem",
    "InvoiceRecord",
    "PayStubRecord",
    "ExtractedRecord",
]
