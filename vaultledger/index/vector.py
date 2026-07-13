"""Vector index: ChromaDB, persistent + local (SPEC.md 7.1, ADR-worthy).

Embeddings are computed by ``OllamaEmbedder`` and passed in explicitly —
Chroma's built-in embedding functions are deliberately unused so the embedding
model stays a single, pinned, local choice. The collection's metadata records
which embedding model built it; querying with a different model raises,
catching the silent index/model mismatch SPEC 15.3 warns about.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from vaultledger.schemas import Chunk

from .embed import OllamaEmbedder

_COLLECTION = "vaultledger_chunks"


class VectorIndex:
    def __init__(self, persist_dir: str | Path, embedder: OllamaEmbedder) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._embedder = embedder

    def build(self, chunks: list[Chunk]) -> int:
        """(Re)build the collection from scratch; returns the number indexed."""
        try:
            self._client.delete_collection(_COLLECTION)
        except Exception:
            pass  # first build: nothing to delete
        collection = self._client.create_collection(
            _COLLECTION, metadata={"embedding_model": self._embedder.model}
        )
        vectors = self._embedder.embed([c.text for c in chunks])
        collection.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "doc_id": c.doc_id,
                    "page": c.page,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                }
                for c in chunks
            ],
        )
        return collection.count()

    def query(self, text: str, k: int = 10) -> list[tuple[str, float]]:
        """Dense top-k: returns (chunk_id, distance) pairs, best first."""
        collection = self._client.get_collection(_COLLECTION)
        built_with = (collection.metadata or {}).get("embedding_model")
        if built_with != self._embedder.model:
            raise RuntimeError(
                f"index built with embedding model {built_with!r}, "
                f"queried with {self._embedder.model!r} — rebuild the index"
            )
        vec = self._embedder.embed([text])[0]
        res = collection.query(query_embeddings=[vec], n_results=k)
        return list(zip(res["ids"][0], res["distances"][0], strict=True))

    def count(self) -> int:
        return self._client.get_collection(_COLLECTION).count()


__all__ = ["VectorIndex"]
