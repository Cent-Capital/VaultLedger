"""Core data contracts for VaultLedger (SPEC.md Section 8.1).

These Pydantic v2 models are contracts: every module reads and writes them
exactly as defined here. If a field changes, it changes here first and the
change ripples out through the type checker.

Deviation from SPEC.md ordering (logged in PROGRESS.md): the spec lists
``Answer`` before the models it references (RoutingDecision, GuardrailEvent,
AgentStep). To keep imports free of forward-reference rebuilds, the leaf
models are defined first and ``Answer`` last. Field names and types are
unchanged from the spec.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Shared type aliases (SPEC 8.1) ---------------------------------------
DocType = Literal["bank_statement", "form_1099", "invoice", "pay_stub", "unknown"]
Tier = Literal["T0", "T1", "T2", "T3"]
Variant = Literal["A_naive", "B_hybrid", "C_graph", "D_agentic"]


# --- Ingestion & retrieval primitives -------------------------------------
class DocMeta(BaseModel):
    doc_id: str
    doc_type: DocType
    source_filename: str
    period_start: date | None = None
    period_end: date | None = None
    is_synthetic: bool = True
    page_count: int
    pii_entity_types: list[str] = Field(default_factory=list)  # e.g. ["PERSON","US_BANK_NUMBER"]


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    page: int
    char_start: int
    char_end: int


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    page: int
    snippet: str  # the exact supporting text


# --- Routing, guardrails, agent steps (referenced by Answer) --------------
class RoutingDecision(BaseModel):
    query_id: str
    allowed_tiers: list[Tier]  # after privacy constraint applied
    chosen_tier: Tier
    chosen_model: str
    reason: str  # human-readable policy trace, e.g. "category=aggregation -> T2; conf ok"
    escalations: int = 0  # 0-2
    est_cost_usd: float
    actual_cost_usd: float


class GuardrailEvent(BaseModel):
    stage: Literal["input", "ingest", "egress", "output"]
    guard: str  # e.g. "pii_redaction", "numeric_verify", "advice_steer"
    action: Literal["pass", "flag", "redact", "block", "downgrade_to_abstain"]
    details: str


class AgentStep(BaseModel):
    step: int
    tool: Literal["retrieve", "calculator", "sql", "finish"]
    input: str
    output_summary: str
    tokens_used: int
    # ADR-0006 amendment: failures are data, not prose hidden in output_summary.
    # None means the tool completed normally; otherwise this carries the stable,
    # queryable failure reason while the partial trace remains valid.
    failure: str | None = None


# --- The answer contract --------------------------------------------------
class Answer(BaseModel):
    # `model_used` collides with Pydantic's protected `model_` namespace; opt out.
    model_config = ConfigDict(protected_namespaces=())

    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    abstained: bool = False
    confidence: float = Field(ge=0, le=1)
    model_used: str  # e.g. "qwen3:8b", "kimi-k2.6", "claude-sonnet"
    tier: Tier
    variant: Variant
    privacy_mode: Literal["local", "cloud"]
    data_left_machine: bool  # drives the UI badge
    routing: RoutingDecision
    guardrail_events: list[GuardrailEvent] = Field(default_factory=list)
    agent_steps: list[AgentStep] = Field(default_factory=list)  # variant D only


# --- Evals contracts ------------------------------------------------------
class QAExample(BaseModel):  # one row of the golden set
    id: str
    question: str
    expected_answer: str
    expected_doc_ids: list[str]
    expected_snippets: list[str]  # must appear in cited chunks
    category: Literal[
        "single_doc",
        "aggregation",
        "unanswerable",
        "adversarial",
        "multi_hop",
        "global_summary",
        "guardrail_benign",
        "cross_persona",
    ]
    difficulty: Literal["easy", "medium", "hard"]
    expected_tier: Tier | None = None  # hand label for router evals (Track B)


class RunManifest(BaseModel):  # one per eval run (SPEC 15.3)
    run_id: str
    timestamp: str
    git_sha: str
    config_hash: str
    golden_set_hash: str
    seed: int
    variant: Variant
    model: str
    metrics: dict[str, float]
    total_cost_usd: float
    failures: list[dict]  # each: {example_id, taxonomy_code, note}


__all__ = [
    "DocType",
    "Tier",
    "Variant",
    "DocMeta",
    "Chunk",
    "Citation",
    "RoutingDecision",
    "GuardrailEvent",
    "AgentStep",
    "Answer",
    "QAExample",
    "RunManifest",
]
