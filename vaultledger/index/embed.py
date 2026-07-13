"""Local embeddings via Ollama (SPEC.md 7.1: ``nomic-embed-text``, fully local).

Talks to the Ollama HTTP API directly — no cloud fallback exists on purpose:
if Ollama is down, embedding fails loudly rather than silently violating the
local-first thesis. The embedding model name is part of the index's identity
(changing it invalidates every stored vector), so it is recorded alongside the
index and checked at query time.
"""

from __future__ import annotations

import requests

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_URL = "http://localhost:11434"


class OllamaEmbedder:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_URL) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed texts in batches; returns one vector per input text."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": batch},
                timeout=120,
            )
            resp.raise_for_status()
            vectors.extend(resp.json()["embeddings"])
        return vectors

    def is_available(self) -> bool:
        """True if Ollama is reachable and the embedding model is present."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            return any(n == self.model or n.startswith(f"{self.model}:") for n in names)
        except requests.RequestException:
            return False


__all__ = ["OllamaEmbedder", "DEFAULT_MODEL", "DEFAULT_URL"]
