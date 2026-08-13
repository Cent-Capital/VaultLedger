"""Variant C: LightRAG local/global retrieval with original-chunk citations."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from vaultledger.config import Config
from vaultledger.graph.ollama_binding import LocalOllamaBinding
from vaultledger.ingest.pipeline import load_chunks
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.schemas import Chunk

GraphQueryMode = Literal["local", "global"]
QueryDataFn = Callable[[str, GraphQueryMode, int], dict[str, Any]]
_PATH_SPLIT_RE = re.compile(r"<SEP>|[|,;]")


def _doc_ids(value: Any) -> list[str]:
    found: list[str] = []
    for part in _PATH_SPLIT_RE.split(str(value or "")):
        doc_id = Path(part.strip()).stem
        if doc_id and doc_id not in found:
            found.append(doc_id)
    return found


def _source_doc_order(result: dict[str, Any]) -> list[str]:
    """Read LightRAG's ranked chunks first, then graph evidence as fallback."""
    if result.get("status") != "success":
        raise RuntimeError(f"LightRAG query failed: {result.get('message', 'unknown error')}")
    data = result.get("data") or {}
    ordered: list[str] = []

    def add(value: Any) -> None:
        for doc_id in _doc_ids(value):
            if doc_id not in ordered:
                ordered.append(doc_id)

    for item in data.get("chunks") or []:
        add(item.get("file_path"))
    for item in data.get("relationships") or []:
        add(item.get("file_path"))
    for item in data.get("entities") or []:
        add(item.get("file_path"))
    for item in data.get("references") or []:
        add(item.get("file_path"))
    return ordered


class LightRAGRetriever:
    """Provider adapter that keeps LightRAG descriptions out of citations.

    LightRAG ranks graph evidence and returns the inserted VaultLedger ``doc_id``
    in ``file_path``. Those ids are mapped back to the exact Phase-2 chunks; the
    generator therefore sees original document text with stable ``#cN`` ids, and
    Phase 5's existing verbatim citation verifier remains unchanged.
    """

    variant = "C_graph"

    def __init__(
        self,
        *,
        index_dir: str | Path,
        working_dir: str | Path,
        model: str,
        embedding_model: str,
        embedding_dim: int,
        base_url: str,
        temperature: float = 0.0,
        top_p: float = 0.95,
        seed: int = 42,
        query_mode: GraphQueryMode = "global",
        query_data_fn: QueryDataFn | None = None,
        chunks: dict[str, Chunk] | None = None,
    ) -> None:
        if query_mode not in {"local", "global"}:
            raise ValueError("LightRAG query_mode must be 'local' or 'global'")
        self.index_dir = Path(index_dir)
        self.working_dir = Path(working_dir)
        self.model = model
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self.query_mode = query_mode
        self._query_data_fn = query_data_fn
        loaded = chunks if chunks is not None else {
            chunk.chunk_id: chunk for chunk in load_chunks(self.index_dir)
        }
        self._chunks_by_doc: dict[str, list[Chunk]] = {}
        for chunk in loaded.values():
            self._chunks_by_doc.setdefault(chunk.doc_id, []).append(chunk)
        for doc_chunks in self._chunks_by_doc.values():
            doc_chunks.sort(key=lambda chunk: (chunk.page, chunk.char_start, chunk.chunk_id))

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        *,
        query_mode: GraphQueryMode | None = None,
        live: bool = False,
    ) -> LightRAGRetriever:
        live_paths = cfg.live_paths() if live else None
        return cls(
            index_dir=(live_paths["index"] if live_paths else cfg.repo_path(cfg.paths.index_dir)),
            working_dir=(
                live_paths["graph"] if live_paths else cfg.repo_path(cfg.graph.working_dir)
            ),
            model=cfg.graph.extraction_model,
            embedding_model=cfg.embedding.model,
            embedding_dim=cfg.graph.embedding_dim,
            base_url=cfg.embedding.ollama_url,
            temperature=cfg.generation.temperature,
            top_p=cfg.generation.top_p,
            seed=cfg.seed,
            query_mode=query_mode or cfg.graph.query_mode_default,
        )

    def _query_data(self, query: str, mode: GraphQueryMode, k: int) -> dict[str, Any]:
        if self._query_data_fn is not None:
            return self._query_data_fn(query, mode, k)
        return asyncio.run(self._query_data_async(query, mode, k))

    async def _query_data_async(
        self,
        query: str,
        mode: GraphQueryMode,
        k: int,
    ) -> dict[str, Any]:
        try:
            from lightrag import LightRAG, QueryParam
            from lightrag.utils import EmbeddingFunc
        except ImportError as exc:  # pragma: no cover - optional install path
            raise RuntimeError("LightRAG is not installed; run `make install-graph`.") from exc

        binding = LocalOllamaBinding(
            model=self.model,
            embedding_model=self.embedding_model,
            base_url=self.base_url,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
        )
        rag = LightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=binding.complete,
            llm_model_name=self.model,
            embedding_func=EmbeddingFunc(
                embedding_dim=self.embedding_dim,
                max_token_size=2048,
                model_name=self.embedding_model,
                func=binding.embed,
            ),
            graph_storage="NetworkXStorage",
            enable_llm_cache=False,
            llm_model_max_async=1,
            embedding_func_max_async=2,
        )
        try:
            await rag.initialize_storages()
            return await rag.aquery_data(
                query,
                QueryParam(
                    mode=mode,
                    top_k=max(k, 20),
                    chunk_top_k=max(k, 20),
                    enable_rerank=False,
                ),
            )
        finally:
            await rag.finalize_storages()

    def retrieve_mode(
        self,
        query: str,
        *,
        mode: GraphQueryMode,
        k: int = 20,
    ) -> list[ScoredChunk]:
        if k < 1:
            return []
        result = self._query_data(query, mode, k)
        ranked: list[ScoredChunk] = []
        seen: set[str] = set()
        for doc_id in _source_doc_order(result):
            for chunk in self._chunks_by_doc.get(doc_id, []):
                if chunk.chunk_id in seen:
                    continue
                rank = len(ranked) + 1
                ranked.append(
                    ScoredChunk(
                        chunk=chunk,
                        score=1.0 / rank,
                        rank=rank,
                        source=f"lightrag_{mode}",
                    )
                )
                seen.add(chunk.chunk_id)
                if len(ranked) >= k:
                    return ranked
        return ranked

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        return self.retrieve_mode(query, mode=self.query_mode, k=k)


__all__ = ["GraphQueryMode", "LightRAGRetriever"]
