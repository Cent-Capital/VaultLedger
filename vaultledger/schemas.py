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
LocalTier = Literal["T0", "T1"]
Variant = Literal["A_naive", "B_hybrid", "C_graph", "D_agentic"]
Corpus = Literal["synthetic", "user"]
PrivacyMode = Literal["local", "cloud"]
GuardrailStage = Literal["input", "ingest", "egress", "output"]
GuardrailAction = Literal["pass", "flag", "redact", "block", "downgrade_to_abstain"]
AgentTool = Literal["retrieve", "calculator", "sql", "finish"]
QuestionCategory = Literal[
    "single_doc",
    "aggregation",
    "unanswerable",
    "adversarial",
    "multi_hop",
    "global_summary",
    "guardrail_benign",
    "cross_persona",
]
Difficulty = Literal["easy", "medium", "hard"]


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
    corpus: Corpus = "synthetic"
    ocr_derived: bool = False
    ocr_pages: list[int] = Field(default_factory=list)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    page: int
    char_start: int
    char_end: int
    corpus: Corpus = "synthetic"
    ocr_derived: bool = False


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    page: int
    snippet: str  # the exact supporting text
    corpus: Corpus = "synthetic"
    ocr_derived: bool = False


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
    stage: GuardrailStage
    guard: str  # e.g. "pii_redaction", "numeric_verify", "advice_steer"
    action: GuardrailAction
    details: str


class AgentStep(BaseModel):
    step: int
    tool: AgentTool
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
    privacy_mode: PrivacyMode
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
    category: QuestionCategory
    difficulty: Difficulty
    expected_tier: Tier | None = None  # hand label for router evals (Track B)


class DecodingProfile(BaseModel):
    """Self-describing local decoding settings for one measured run."""

    temperature: float
    top_p: float
    top_k: int | None = Field(default=None, ge=1)
    seed: int
    num_ctx: int
    max_tokens: int | None = Field(default=None, ge=1)
    think: bool = False
    transport: Literal["ollama_chat"] = "ollama_chat"


class ModelMetadata(BaseModel):
    """Ollama-reported identity and resource metadata for one model tag."""

    parameter_count: str = Field(min_length=1)
    quantization: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    family: str = Field(min_length=1)
    artifact_size_bytes: int = Field(gt=0)
    resident_size_bytes: int = Field(gt=0)
    resident_size_vram_bytes: int = Field(ge=0)
    ollama_version: str = Field(min_length=1)


class MatrixJudgeVerdict(BaseModel):
    """One rubric verdict retained with its required human-readable reason."""

    example_id: str
    passed: bool
    reason: str
    failure_code: Literal[
        "NONE",
        "INCORRECT",
        "UNSUPPORTED",
        "FALSE_ABSTAIN",
        "INJECTION",
        "OTHER",
    ]


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
    decoding: DecodingProfile | None = None
    prompt_sha256: str | None = None
    model_metadata: ModelMetadata | None = None
    judge_model: str | None = None
    judge_verdicts: list[MatrixJudgeVerdict] = Field(default_factory=list)


__all__ = [
    "DocType",
    "Tier",
    "LocalTier",
    "Variant",
    "Corpus",
    "PrivacyMode",
    "GuardrailStage",
    "GuardrailAction",
    "AgentTool",
    "QuestionCategory",
    "Difficulty",
    "DocMeta",
    "Chunk",
    "Citation",
    "RoutingDecision",
    "GuardrailEvent",
    "AgentStep",
    "Answer",
    "QAExample",
    "DecodingProfile",
    "ModelMetadata",
    "MatrixJudgeVerdict",
    "RunManifest",
]
