"""Pure output guards plus SQLite record-of-truth adapters (SPEC 13.3)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from vaultledger.guardrails.input import EDUCATION_NOT_ADVICE_RESPONSE
from vaultledger.schemas import Citation, GuardrailEvent

_MONEY = re.compile(r"\$([\d,]+\.\d{2})")
_ADVICE_OUTPUT = re.compile(
    r"(?i)\b(?:you\s+should|i\s+recommend|buy|sell|invest\s+in|best\s+investment)\b"
)


@dataclass(frozen=True)
class InvoiceTotal:
    doc_id: str
    invoice_number: str
    printed_total: float
    line_item_sum: float


@dataclass(frozen=True)
class Persona:
    name: str
    account_last4: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputGuardResult:
    events: tuple[GuardrailEvent, ...]
    blocked: bool = False
    downgrade_to_abstain: bool = False
    replacement_text: str | None = None


def load_invoice_totals(
    db_path: str | Path, doc_ids: set[str]
) -> list[InvoiceTotal]:
    if not doc_ids or not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""SELECT i.doc_id, i.invoice_number, i.total AS printed_total,
                   COALESCE(SUM(li.amount), 0) AS line_item_sum
            FROM invoices i
            LEFT JOIN invoice_line_items li ON li.doc_id = i.doc_id
            WHERE i.doc_id IN ({placeholders})
            GROUP BY i.doc_id, i.invoice_number, i.total""",  # noqa: S608 - placeholders only
        tuple(sorted(doc_ids)),
    ).fetchall()
    conn.close()
    return [
        InvoiceTotal(
            doc_id=row["doc_id"],
            invoice_number=row["invoice_number"],
            printed_total=float(row["printed_total"]),
            line_item_sum=round(float(row["line_item_sum"]), 2),
        )
        for row in rows
    ]


def numeric_verify(
    question: str,
    answer_text: str,
    totals: list[InvoiceTotal],
    *,
    epsilon: float,
) -> OutputGuardResult:
    mismatches = [
        total
        for total in totals
        if abs(total.printed_total - total.line_item_sum) > epsilon
    ]
    if not mismatches:
        return OutputGuardResult(
            events=(GuardrailEvent(
                stage="output",
                guard="numeric_verify",
                action="pass",
                details="no cited invoice total mismatch",
            ),)
        )

    events: list[GuardrailEvent] = []
    unsafe = False
    values = {float(value.replace(",", "")) for value in _MONEY.findall(answer_text)}
    text = answer_text.casefold()
    asks_printed = "printed total" in question.casefold()
    for total in mismatches:
        delta = round(abs(total.printed_total - total.line_item_sum), 2)
        acknowledges = (
            asks_printed
            or (
                any(
                    word in text
                    for word in ("discrep", "mismatch", "line item", "higher", "lower")
                )
                and any(
                    abs(value - expected) <= epsilon
                    for value in values
                    for expected in (total.printed_total, total.line_item_sum, delta)
                )
            )
        )
        events.append(
            GuardrailEvent(
                stage="output",
                guard="numeric_verify",
                action="flag",
                details=(
                    f"{total.invoice_number}: printed ${total.printed_total:,.2f} vs "
                    f"line-item sum ${total.line_item_sum:,.2f}"
                ),
            )
        )
        unsafe |= not acknowledges
    if unsafe:
        events.append(
            GuardrailEvent(
                stage="output",
                guard="numeric_verify",
                action="downgrade_to_abstain",
                details=(
                    "answer did not disclose a cited invoice's arithmetic mismatch "
                    "[NUM_MISMATCH]"
                ),
            )
        )
    return OutputGuardResult(tuple(events), downgrade_to_abstain=unsafe)


def load_personas(db_path: str | Path) -> list[Persona]:
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    names = {
        row[0]
        for query in (
            "SELECT DISTINCT account_holder FROM bank_statements",
            "SELECT DISTINCT recipient_name FROM forms_1099",
            "SELECT DISTINCT employee FROM pay_stubs",
        )
        for row in conn.execute(query)
    }
    personas = []
    for name in sorted(names):
        accounts = tuple(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT account_last4 FROM bank_statements WHERE account_holder = ?",
                (name,),
            )
        )
        personas.append(Persona(name, accounts))
    conn.close()
    return personas


def cross_persona_check(
    question: str, answer_text: str, personas: list[Persona]
) -> OutputGuardResult:
    question_folded = question.casefold()
    subjects = [persona for persona in personas if persona.name.casefold() in question_folded]
    leaks: list[str] = []
    if len(subjects) == 1:
        subject = subjects[0]
        answer_folded = answer_text.casefold()
        for persona in personas:
            if persona == subject:
                continue
            if persona.name.casefold() in answer_folded:
                leaks.append(persona.name)
            leaks.extend(
                f"masked account ****{last4}"
                for last4 in persona.account_last4
                if f"****{last4}" in answer_text
            )
    event = GuardrailEvent(
        stage="output",
        guard="cross_persona_check",
        action="block" if leaks else "pass",
        details=(
            "blocked other-persona PII: " + ", ".join(sorted(set(leaks)))
            if leaks
            else "no other-persona tagged PII detected"
        ),
    )
    return OutputGuardResult(
        events=(event,), blocked=bool(leaks), downgrade_to_abstain=bool(leaks)
    )


def advice_linter(answer_text: str) -> OutputGuardResult:
    found = bool(_ADVICE_OUTPUT.search(answer_text))
    return OutputGuardResult(
        events=(GuardrailEvent(
            stage="output",
            guard="advice_linter",
            action="downgrade_to_abstain" if found else "pass",
            details=(
                "prescriptive advice phrasing replaced with fixed boundary response"
                if found
                else "no prescriptive advice phrasing detected"
            ),
        ),),
        downgrade_to_abstain=found,
        replacement_text=EDUCATION_NOT_ADVICE_RESPONSE if found else None,
    )


def cited_doc_ids(citations: list[Citation]) -> set[str]:
    return {citation.doc_id for citation in citations}


__all__ = [
    "InvoiceTotal",
    "OutputGuardResult",
    "Persona",
    "advice_linter",
    "cited_doc_ids",
    "cross_persona_check",
    "load_invoice_totals",
    "load_personas",
    "numeric_verify",
]
