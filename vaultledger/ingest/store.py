"""Typed-record store: extracted records -> SQLite (SPEC.md Sections 7.1, 8.2).

Tables mirror the Section 8.2 record schemas, one parent table per doc type
plus child tables for their repeated parts (transactions, line items, boxes,
deductions). Three later consumers read this store: the agentic ``sql`` tool
(SELECT-only), the numeric verifier, and ground-truth scoring — so amounts are
stored as REAL columns, never JSON blobs, to stay queryable.

An ingest run rebuilds the store from scratch (it is derived data; the PDFs
and ground truth are the sources of record), so the schema is dropped and
recreated rather than migrated.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vaultledger.schemas import DocMeta, GuardrailEvent

from .records import (
    ExtractedRecord,
    Form1099Record,
    InvoiceRecord,
    PayStubRecord,
    StatementRecord,
)

_SCHEMA = """
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS bank_statements;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS forms_1099;
DROP TABLE IF EXISTS form_1099_boxes;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS invoice_line_items;
DROP TABLE IF EXISTS pay_stubs;
DROP TABLE IF EXISTS pay_stub_deductions;

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1,
    page_count INTEGER NOT NULL,
    pii_entity_types TEXT NOT NULL DEFAULT '[]',  -- JSON array of entity type names
    guardrail_events TEXT NOT NULL DEFAULT '[]',
    parse_status TEXT NOT NULL,                   -- 'ok' | 'failed'
    error TEXT
);

CREATE TABLE bank_statements (
    doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
    account_holder TEXT NOT NULL,
    account_last4 TEXT NOT NULL,
    account_type TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    opening_balance REAL NOT NULL,
    closing_balance REAL NOT NULL
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES bank_statements(doc_id),
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('debit', 'credit'))
);

CREATE TABLE forms_1099 (
    doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
    payer_name TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    tax_year INTEGER NOT NULL
);

CREATE TABLE form_1099_boxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES forms_1099(doc_id),
    box TEXT NOT NULL,
    amount REAL NOT NULL
);

CREATE TABLE invoices (
    doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
    vendor TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    issue_date TEXT,           -- layout B does not print one
    due_date TEXT NOT NULL,
    total REAL NOT NULL        -- printed total; numeric verifier re-checks it
);

CREATE TABLE invoice_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES invoices(doc_id),
    desc TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    amount REAL NOT NULL
);

CREATE TABLE pay_stubs (
    doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
    employer TEXT NOT NULL,
    employee TEXT NOT NULL,
    pay_period TEXT NOT NULL,
    pay_date TEXT,
    gross_pay REAL NOT NULL,
    net_pay REAL NOT NULL
);

CREATE TABLE pay_stub_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES pay_stubs(doc_id),
    name TEXT NOT NULL,
    amount REAL NOT NULL
);
"""


class RecordStore:
    """Writer/reader for the typed-record SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def write_document(
        self,
        meta: DocMeta,
        parse_status: str,
        error: str | None = None,
        guardrail_events: list[GuardrailEvent] | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                meta.doc_id,
                meta.doc_type,
                meta.source_filename,
                meta.period_start.isoformat() if meta.period_start else None,
                meta.period_end.isoformat() if meta.period_end else None,
                int(meta.is_synthetic),
                meta.page_count,
                json.dumps(meta.pii_entity_types),
                json.dumps([event.model_dump() for event in guardrail_events or []]),
                parse_status,
                error,
            ),
        )
        self._conn.commit()

    def write_record(self, doc_id: str, record: ExtractedRecord) -> None:
        c = self._conn
        if isinstance(record, StatementRecord):
            c.execute(
                "INSERT INTO bank_statements VALUES (?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    record.account_holder,
                    record.account_last4,
                    record.account_type,
                    record.period_start.isoformat(),
                    record.period_end.isoformat(),
                    record.opening_balance,
                    record.closing_balance,
                ),
            )
            c.executemany(
                "INSERT INTO transactions (doc_id, date, description, amount, type) "
                "VALUES (?,?,?,?,?)",
                [
                    (doc_id, t.date.isoformat(), t.description, t.amount, t.type)
                    for t in record.transactions
                ],
            )
        elif isinstance(record, Form1099Record):
            c.execute(
                "INSERT INTO forms_1099 VALUES (?,?,?,?)",
                (doc_id, record.payer_name, record.recipient_name, record.tax_year),
            )
            c.executemany(
                "INSERT INTO form_1099_boxes (doc_id, box, amount) VALUES (?,?,?)",
                [(doc_id, box, amount) for box, amount in record.box_amounts.items()],
            )
        elif isinstance(record, InvoiceRecord):
            c.execute(
                "INSERT INTO invoices VALUES (?,?,?,?,?,?)",
                (
                    doc_id,
                    record.vendor,
                    record.invoice_number,
                    record.issue_date.isoformat() if record.issue_date else None,
                    record.due_date.isoformat(),
                    record.total,
                ),
            )
            c.executemany(
                "INSERT INTO invoice_line_items (doc_id, desc, qty, unit_price, amount) "
                "VALUES (?,?,?,?,?)",
                [(doc_id, li.desc, li.qty, li.unit_price, li.amount) for li in record.line_items],
            )
        elif isinstance(record, PayStubRecord):
            c.execute(
                "INSERT INTO pay_stubs VALUES (?,?,?,?,?,?,?)",
                (
                    doc_id,
                    record.employer,
                    record.employee,
                    record.pay_period,
                    record.pay_date.isoformat() if record.pay_date else None,
                    record.gross_pay,
                    record.net_pay,
                ),
            )
            c.executemany(
                "INSERT INTO pay_stub_deductions (doc_id, name, amount) VALUES (?,?,?)",
                [(doc_id, name, amount) for name, amount in record.deductions.items()],
            )
        else:  # pragma: no cover - the type union above is exhaustive
            raise TypeError(f"unsupported record type: {type(record).__name__}")
        c.commit()

    def connect(self) -> sqlite3.Connection:
        """Direct read access (tests, sql tool, numeric verifier)."""
        return self._conn

    def close(self) -> None:
        self._conn.close()


__all__ = ["RecordStore"]
