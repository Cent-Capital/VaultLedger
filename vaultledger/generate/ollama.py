"""Local Ollama chat generation shared by the product and eval gateway."""

from __future__ import annotations

import requests


def ollama_chat_payload(
    *,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    seed: int,
    num_ctx: int,
    fmt: dict | str | None = None,
    max_tokens: int | None = None,
    system_prompt: str | None = None,
    history_messages: list[dict[str, str]] | None = None,
) -> dict:
    """Build the one decoding payload every active Ollama generator uses."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})
    payload: dict = {
        "model": ollama_model_name(model),
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "seed": seed,
            "num_ctx": num_ctx,
        },
    }
    if fmt is not None:
        payload["format"] = fmt
    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens
    return payload


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
        num_ctx: int = 32768,
    ) -> None:
        self.model = ollama_model_name(model)
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self.num_ctx = num_ctx

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
        payload = ollama_chat_payload(
            model=self.model,
            prompt=prompt,
            temperature=self.temperature if temperature is None else temperature,
            top_p=self.top_p,
            seed=self.seed,
            num_ctx=self.num_ctx,
            fmt=fmt,
            max_tokens=max_tokens,
        )
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat", json=payload, timeout=180
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GenerationError(str(exc)) from exc
        return str(resp.json().get("message", {}).get("content", "")).strip()


__all__ = [
    "GenerationError",
    "OllamaGenerator",
    "ollama_chat_payload",
    "ollama_model_name",
]
