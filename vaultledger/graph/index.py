"""Build a citation-preserving local LightRAG index and write its cost receipt."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from vaultledger.config import Config
from vaultledger.ingest.pipeline import load_chunks
from vaultledger.schemas import Chunk

from .ollama_binding import LocalOllamaBinding


def documents_from_chunks(index_dir: str | Path) -> tuple[list[str], list[str]]:
    """Assemble one stable LightRAG input document per VaultLedger doc id."""
    grouped: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for chunk in load_chunks(index_dir):
        grouped[chunk.doc_id].append((chunk.page, chunk.char_start, chunk.text))
    ids = sorted(grouped)
    documents = [
        "\n\n".join(text for _, _, text in sorted(grouped[doc_id])) for doc_id in ids
    ]
    return ids, documents


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


async def _ainsert_one(
    rag: object,
    *,
    doc_id: str,
    document: str,
    replace_existing: bool = False,
) -> None:
    """Insert exactly one stable-id document into an initialized LightRAG store."""
    await rag.initialize_storages()  # type: ignore[attr-defined]
    try:
        if replace_existing:
            deletion = await rag.adelete_by_doc_id(doc_id)  # type: ignore[attr-defined]
            status = getattr(deletion, "status", None)
            if status not in {"success", "not_found"}:
                raise RuntimeError(
                    f"LightRAG could not replace {doc_id}: deletion status={status!r}"
                )
        await rag.ainsert(  # type: ignore[attr-defined]
            [document],
            ids=[doc_id],
            file_paths=[doc_id],
        )
    finally:
        await rag.finalize_storages()  # type: ignore[attr-defined]


async def insert_lightrag_document(
    cfg: Config,
    *,
    doc_id: str,
    chunks: list[Chunk],
    working_dir: str | Path,
    replace_existing: bool = False,
) -> dict:
    """Incrementally insert one live document and return measured local usage."""
    try:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
    except ImportError as exc:  # pragma: no cover - optional install path
        raise RuntimeError("LightRAG is not installed; run `make install-graph`.") from exc

    if not chunks:
        raise ValueError(f"cannot graph-index {doc_id}: document has no readable chunks")
    ordered = sorted(chunks, key=lambda chunk: (chunk.page, chunk.char_start, chunk.chunk_id))
    document = "\n\n".join(chunk.text for chunk in ordered)
    destination = Path(working_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    binding = LocalOllamaBinding(
        model=cfg.graph.extraction_model,
        embedding_model=cfg.embedding.model,
        base_url=cfg.embedding.ollama_url,
        temperature=cfg.generation.temperature,
        top_p=cfg.generation.top_p,
        seed=cfg.seed,
        num_ctx=cfg.generation.num_ctx,
    )
    rag = LightRAG(
        working_dir=str(destination),
        llm_model_func=binding.complete,
        llm_model_name=cfg.graph.extraction_model,
        embedding_func=EmbeddingFunc(
            embedding_dim=cfg.graph.embedding_dim,
            max_token_size=2048,
            model_name=cfg.embedding.model,
            func=binding.embed,
        ),
        graph_storage="NetworkXStorage",
        entity_extraction_use_json=True,
        entity_extract_max_gleaning=1,
        llm_model_max_async=1,
        embedding_func_max_async=2,
        max_parallel_insert=1,
        addon_params={
            "language": "English",
            "entity_types_guidance": (
                "- Person: account holders, employees, contractors, invoice issuers\n"
                "- Organization: employers, clients, payers, banks, merchants\n"
                "- Account: checking or savings accounts identified by masked last four digits"
            ),
        },
    )
    started = perf_counter()
    await _ainsert_one(
        rag,
        doc_id=doc_id,
        document=document,
        replace_existing=replace_existing,
    )
    wall_ms = round((perf_counter() - started) * 1000, 3)
    usage = binding.usage()
    return {
        "doc_id": doc_id,
        "wall_latency_ms": wall_ms,
        "completion_calls": usage.completion_calls,
        "embedding_calls": usage.embedding_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "provider_latency_ms": usage.latency_ms,
        "total_cost_usd": usage.cost_usd,
        "pricing_status": usage.pricing_status,
    }


async def build_lightrag_index(
    cfg: Config,
    *,
    document_limit: int = 0,
) -> dict:
    """Build once into an empty directory; never overwrite extraction evidence."""
    try:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
    except ImportError as exc:  # pragma: no cover - optional install path
        raise RuntimeError("LightRAG is not installed; run `make install-graph`.") from exc

    working_dir = cfg.repo_path(cfg.graph.working_dir)
    if working_dir.exists() and any(working_dir.iterdir()):
        raise FileExistsError(
            f"graph index already exists at {working_dir}; move it aside before rebuilding"
        )
    working_dir.mkdir(parents=True, exist_ok=True)
    index_dir = cfg.repo_path(cfg.paths.index_dir)
    ids, documents = documents_from_chunks(index_dir)
    if document_limit > 0:
        ids, documents = ids[:document_limit], documents[:document_limit]
    if not ids:
        raise FileNotFoundError(f"no chunks found in {index_dir}; run `make ingest` first")

    binding = LocalOllamaBinding(
        model=cfg.graph.extraction_model,
        embedding_model=cfg.embedding.model,
        base_url=cfg.embedding.ollama_url,
        temperature=cfg.generation.temperature,
        top_p=cfg.generation.top_p,
        seed=cfg.seed,
        num_ctx=cfg.generation.num_ctx,
    )
    embedding = EmbeddingFunc(
        embedding_dim=cfg.graph.embedding_dim,
        max_token_size=2048,
        model_name=cfg.embedding.model,
        func=binding.embed,
    )
    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=binding.complete,
        llm_model_name=cfg.graph.extraction_model,
        embedding_func=embedding,
        graph_storage="NetworkXStorage",
        entity_extraction_use_json=True,
        entity_extract_max_gleaning=1,
        llm_model_max_async=1,
        embedding_func_max_async=2,
        max_parallel_insert=1,
        addon_params={
            "language": "English",
            "entity_types_guidance": (
                "- Person: account holders, employees, contractors, invoice issuers\n"
                "- Organization: employers, clients, payers, banks, merchants\n"
                "- Account: checking or savings accounts identified by masked last four digits"
            ),
        },
    )
    started = perf_counter()
    try:
        await rag.initialize_storages()
        await rag.ainsert(documents, ids=ids, file_paths=ids)
    finally:
        await rag.finalize_storages()
    wall_ms = round((perf_counter() - started) * 1000, 3)

    graphmls = sorted(working_dir.rglob("*.graphml"))
    if len(graphmls) != 1:
        raise RuntimeError(f"expected one LightRAG GraphML artifact, found {len(graphmls)}")
    usage = binding.usage()
    timestamp = datetime.now(UTC).isoformat()
    run_id = hashlib.sha256(
        f"{timestamp}:{_git_sha(cfg.repo_path('.'))}:{len(ids)}".encode()
    ).hexdigest()[:12]
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "git_sha": _git_sha(cfg.repo_path(".")),
        "engine": "lightrag",
        "engine_version": importlib.metadata.version("lightrag-hku"),
        "extraction_model": cfg.graph.extraction_model,
        "embedding_model": cfg.embedding.model,
        "config_hash": _sha256(cfg.repo_path("config.yaml")),
        "corpus_hash": _sha256(index_dir / "chunks.jsonl"),
        "documents_indexed": len(ids),
        "graphml": _display_path(graphmls[0], cfg.repo_path(".")),
        "wall_latency_ms": wall_ms,
        "completion_calls": usage.completion_calls,
        "embedding_calls": usage.embedding_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "provider_latency_ms": usage.latency_ms,
        "total_cost_usd": usage.cost_usd,
        "pricing_status": usage.pricing_status,
        "cost_note": "Local inference is unpriced, not free; latency and tokens are recorded.",
    }


def write_index_receipt(receipt: dict, reports_dir: str | Path) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"phase15_graph_index_{receipt['run_id']}.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path


__all__ = [
    "_ainsert_one",
    "build_lightrag_index",
    "documents_from_chunks",
    "insert_lightrag_document",
    "write_index_receipt",
]
