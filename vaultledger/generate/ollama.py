"""Minimal local generation wrapper for Phase 3."""

from __future__ import annotations

import requests


class GenerationError(RuntimeError):
    """Raised when the local model cannot generate an answer."""


def ollama_model_name(model_id: str) -> str:
    """Convert config model ids like ``ollama/qwen3:8b`` to Ollama names."""
    return model_id.removeprefix("ollama/")


class OllamaGenerator:
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = ollama_model_name(model)
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            return any(n == self.model or n.startswith(f"{self.model}:") for n in names)
        except requests.RequestException:
            return False

    def generate(self, prompt: str, *, temperature: float = 0.0) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=180,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GenerationError(str(exc)) from exc
        return str(resp.json().get("response", "")).strip()


__all__ = ["GenerationError", "OllamaGenerator", "ollama_model_name"]
