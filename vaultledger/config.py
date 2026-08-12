"""Typed configuration loader (SPEC.md 7.1 "Config" + Appendix B).

One ``config.yaml`` drives every knob in the system. This module validates it
into typed objects so a bad config fails loudly at startup, not deep inside a
loop. Loading order (pydantic-settings sources): explicit init kwargs >
config.yaml > environment > .env > secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

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
    agent_steps_max: int = Field(ge=1)
    agent_tokens_max: int = Field(ge=1)
    agent_output_tokens_max: int = Field(ge=1)
    agent_seconds_max: float = Field(gt=0)


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

    The full six-model lineup is deliberately pinned at Phase 18 kickoff. The
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
    context_budget_chars: int = Field(default=12_000, ge=1)


class Embedding(BaseModel):
    model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"


class Graph(BaseModel):
    """Phase 15 local-only GraphRAG configuration (ADR-0008)."""

    engine: str = "lightrag"
    extraction_model: str = "ollama/qwen3:8b"
    embedding_dim: int = Field(default=768, ge=1)
    query_mode_default: Literal["local", "global"] = "global"
    answer_top_n: int = Field(default=12, ge=1)
    working_dir: str = "data/graph/lightrag"
    obsidian_dir: str = "exports/obsidian_vault"
    entity_recall_min: float = Field(default=0.80, ge=0, le=1)


class Chunking(BaseModel):
    max_chars: int = 2400  # ~600 tokens at ~4 chars/token (SPEC 8.4: 500-800)
    overlap_frac: float = 0.15


class Paths(BaseModel):
    """Repo-relative data locations (resolve via ``Config.repo_path``)."""

    pdfs: str = "data/synthetic_pdfs"
    ground_truth: str = "data/ground_truth"
    index_dir: str = "data/index"  # derived, rebuildable, gitignored
    traces: str = "data/traces"


class LiveDocuments(BaseModel):
    """Phase 16 user-document locations and bounded watcher/OCR settings.

    These paths intentionally do not reuse ``Paths``: the synthetic corpus is
    reproducible evaluation input, while user documents and every derivative of
    them must live outside the public repository (ADR-0011).
    """

    inbox_dir: str = "~/VaultLedger/Inbox"
    index_dir: str = "~/VaultLedger/index"
    graph_working_dir: str = "~/VaultLedger/graph"
    obsidian_dir: str = "~/VaultLedger/obsidian_vault"
    traces_dir: str = "~/VaultLedger/traces"
    watcher_poll_seconds: float = Field(default=1.0, gt=0)
    watcher_stable_polls: int = Field(default=2, ge=2)
    watcher_max_polls: int = Field(default=3600, ge=1)
    ocr_timeout_seconds: float = Field(default=300.0, gt=0)
    graph_timeout_seconds: float = Field(default=900.0, gt=0)


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
    graph: Graph = Graph()
    chunking: Chunking = Chunking()
    paths: Paths = Paths()
    live: LiveDocuments = LiveDocuments()

    def repo_path(self, rel: str) -> Path:
        """Resolve a repo-relative path from config against the repo root."""
        return REPO_ROOT / rel

    def live_paths(self) -> dict[str, Path]:
        """Resolve and validate every user-data path before any live-data I/O.

        ``~`` is accepted in the human-edited YAML because ADR-0011 specifies
        that portable default. The returned paths are absolute and resolved.
        No path may be the repository or one of its descendants, and live roots
        may not contain one another: source PDFs and derived text must remain
        visibly separate.
        """
        raw = {
            "inbox": self.live.inbox_dir,
            "index": self.live.index_dir,
            "graph": self.live.graph_working_dir,
            "obsidian": self.live.obsidian_dir,
            "traces": self.live.traces_dir,
        }
        resolved = {
            name: Path(value).expanduser().resolve(strict=False)
            for name, value in raw.items()
        }
        repo_root = REPO_ROOT.resolve()
        for name, path in resolved.items():
            if path == repo_root or path.is_relative_to(repo_root):
                raise ValueError(
                    f"live {name} path must be outside the repository: {path}"
                )
            if not path.is_absolute():  # defensive; resolve() is absolute
                raise ValueError(f"live {name} path must resolve to an absolute path: {path}")
        names = sorted(resolved)
        for index, left_name in enumerate(names):
            left = resolved[left_name]
            for right_name in names[index + 1 :]:
                right = resolved[right_name]
                if left.is_relative_to(right) or right.is_relative_to(left):
                    raise ValueError(
                        "live paths must not contain one another: "
                        f"{left_name}={left}, {right_name}={right}"
                    )
        return resolved

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
    "Graph",
    "Chunking",
    "Paths",
    "LiveDocuments",
    "load_config",
    "CONFIG_PATH",
    "REPO_ROOT",
]
