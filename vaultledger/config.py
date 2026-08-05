"""Typed configuration loader (SPEC.md 7.1 "Config" + Appendix B).

One ``config.yaml`` drives every knob in the system. This module validates it
into typed objects so a bad config fails loudly at startup, not deep inside a
loop. Loading order (pydantic-settings sources): explicit init kwargs >
config.yaml > environment > .env > secrets.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Repo root is one level above this package directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


class Budgets(BaseModel):
    session_usd: float
    project_usd: float


class Loops(BaseModel):
    repair_max: int
    retrieval_retry_max: int
    escalations_max: int
    agent_steps_max: int


class Thresholds(BaseModel):
    rerank_tau: float
    numeric_epsilon: float
    over_refusal_max: float


class ModelRef(BaseModel):
    id: str


class ModelRegistry(BaseModel):
    T0: ModelRef
    T1: ModelRef
    matrix: list[ModelRef] = Field(min_length=1)


class Matrix(BaseModel):
    """Phase 11 local model-matrix defaults.

    The full six-model lineup is deliberately pinned at Phase 17 kickoff. The
    two models here prove the matrix machinery without claiming the deferred
    bake-off has happened.
    """

    variants: list[str] = ["B_hybrid"]
    smoke_limit: int = Field(default=12, ge=0)


class Router(BaseModel):
    """Phase 12 deterministic local-size routing policy."""

    t0_categories: list[str] = ["single_doc", "guardrail_benign"]
    projected_cost_usd: dict[str, float] = {"T0": 0.0, "T1": 0.0}


class Guardrails(BaseModel):
    """Phase 13 named guard toggles (ADR-0005)."""

    file_validation: bool = True
    pii_tagging: bool = True
    injection_scan: bool = True
    query_injection_guard: bool = True
    advice_steer: bool = True
    egress_redaction: bool = True
    citation_verify: bool = True
    numeric_verify: bool = True
    cross_persona_check: bool = True
    advice_linter: bool = True
    max_upload_bytes: int = Field(default=10_000_000, gt=0)


class Reranker(BaseModel):
    enabled: bool = True
    model: str = "BAAI/bge-reranker-base"
    batch_size: int = 16


class Retrieval(BaseModel):
    candidate_k: int = 20
    rrf_constant: int = 60
    answer_top_n: int = 6


class Generation(BaseModel):
    """Phase 5 structured-output + citation-verification knobs."""

    # Minimum normalized snippet length a citation must carry to be verifiable.
    min_snippet_chars: int = 16
    litm_reorder: bool = True


class Embedding(BaseModel):
    model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"


class Chunking(BaseModel):
    max_chars: int = 2400  # ~600 tokens at ~4 chars/token (SPEC 8.4: 500-800)
    overlap_frac: float = 0.15


class Paths(BaseModel):
    """Repo-relative data locations (resolve via ``Config.repo_path``)."""

    pdfs: str = "data/synthetic_pdfs"
    ground_truth: str = "data/ground_truth"
    index_dir: str = "data/index"  # derived, rebuildable, gitignored
    traces: str = "data/traces"


class Config(BaseSettings):
    """Validated view of ``config.yaml``."""

    model_config = SettingsConfigDict(
        yaml_file=str(CONFIG_PATH),
        extra="ignore",
    )

    seed: int = 42
    budgets: Budgets
    loops: Loops
    thresholds: Thresholds
    models: ModelRegistry
    matrix: Matrix = Matrix()
    router: Router = Router()
    guardrails: Guardrails = Guardrails()
    variant_default: str = "B_hybrid"
    reranker: Reranker = Reranker()
    retrieval: Retrieval = Retrieval()
    generation: Generation = Generation()
    embedding: Embedding = Embedding()
    chunking: Chunking = Chunking()
    paths: Paths = Paths()

    def repo_path(self, rel: str) -> Path:
        """Resolve a repo-relative path from config against the repo root."""
        return REPO_ROOT / rel

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Put YAML ahead of env so config.yaml is the canonical source, while
        # still letting an explicit env var override for CI / one-off runs.
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate configuration.

    With no argument, reads the repo-root ``config.yaml``. Pass ``path`` to
    load an alternate config (used in tests and matrix runs).
    """
    if path is None:
        return Config()
    data = yaml.safe_load(Path(path).read_text()) or {}
    return Config.model_validate(data)


__all__ = [
    "Config",
    "Budgets",
    "Loops",
    "Thresholds",
    "ModelRef",
    "ModelRegistry",
    "Matrix",
    "Router",
    "Guardrails",
    "Reranker",
    "Retrieval",
    "Generation",
    "Embedding",
    "Chunking",
    "Paths",
    "load_config",
    "CONFIG_PATH",
    "REPO_ROOT",
]
