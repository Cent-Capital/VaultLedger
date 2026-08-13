"""Minimal local generation wrapper for Phase 3."""

from __future__ import annotations

import requests


class GenerationError(RuntimeError):
    """Raised when the local model cannot generate an answer."""


def ollama_model_name(model_id: str) -> str:
    """Convert config model ids like ``ollama/qwen3:8b`` to Ollama names."""
    return model_id.removeprefix("ollama/")


class OllamaGenerator:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        temperature: float = 0.0,
        top_p: float = 0.95,
        seed: int = 42,
    ) -> None:
        self.model = ollama_model_name(model)
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            return any(n == self.model or n.startswith(f"{self.model}:") for n in names)
        except requests.RequestException:
            return False

    def generate(self, prompt: str, *, temperature: float | None = None) -> str:
        return self._generate(prompt, temperature=temperature)

    def generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate with Ollama's constrained JSON decoding (``format`` = schema).

        Passing the JSON Schema makes the runtime emit schema-shaped JSON, which
        is the Phase 5 alternative to the ``instructor`` library (see ADR-0002).
        The output is still validated and repaired upstream — constrained
        decoding narrows failures, it does not eliminate them.
        """
        return self._generate(
            prompt, temperature=temperature, fmt=schema, max_tokens=max_tokens
        )

    def _generate(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        fmt: dict | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Qwen 3 defaults to thinking in Ollama, and thinking tokens are
            # charged against `num_predict` before any answer is emitted. The
            # matrix gateway has disabled it since Phase 11; this path had not,
            # so the product and the Phase 7/14 safety runner were measuring a
            # different system from the one the matrix scored. Measured on
            # qwen3:8b at num_predict=64: thinking on returns `response=""` with
            # done_reason "length"; thinking off returns valid JSON and stops
            # cleanly. Variant D's planner therefore received empty strings and
            # recorded them as planner errors until its whole step budget was
            # gone. Any generator the product uses must match the gateway's
            # decoding settings or the evals measure something else (ADR-0007).
            "think": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "top_p": self.top_p,
                # RunManifest.seed used to describe a knob that never reached
                # inference. Phase 18 makes the recorded value operative.
                "seed": self.seed,
            },
        }
        if fmt is not None:
            payload["format"] = fmt
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=180
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GenerationError(str(exc)) from exc
        return str(resp.json().get("response", "")).strip()


__all__ = ["GenerationError", "OllamaGenerator", "ollama_model_name"]
