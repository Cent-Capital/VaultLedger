"""Local Ollama chat generation shared by the product and eval gateway."""

from __future__ import annotations

import requests

from vaultledger.ollama_payload import ollama_chat_payload, ollama_model_name
from vaultledger.schemas import ModelMetadata


class GenerationError(RuntimeError):
    """Raised when the local model cannot generate an answer."""


def ollama_warm_model(
    model_id: str,
    *,
    base_url: str = "http://localhost:11434",
    temperature: float = 0.0,
    top_p: float = 0.95,
    top_k: int = 20,
    seed: int = 42,
    num_ctx: int = 8192,
    keep_alive: str = "10m",
    timeout: int = 600,
) -> None:
    """Load a candidate without generating, so cold load is not a scored failure."""
    payload = {
        "model": ollama_model_name(model_id),
        "prompt": "",
        "stream": False,
        "keep_alive": keep_alive,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "seed": seed,
            "num_ctx": num_ctx,
        },
    }
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GenerationError(
            f"could not pre-warm Ollama model {ollama_model_name(model_id)}: {exc}"
        ) from exc


def _same_ollama_tag(candidate: str, expected: str) -> bool:
    return candidate == expected or (
        ":" not in expected and candidate == f"{expected}:latest"
    )


def ollama_model_metadata(
    model_id: str,
    *,
    base_url: str = "http://localhost:11434",
) -> ModelMetadata:
    """Read identity from show/tags and resident bytes from the loaded model."""
    model = ollama_model_name(model_id)
    root = base_url.rstrip("/")
    try:
        show_response = requests.post(
            f"{root}/api/show", json={"model": model}, timeout=30
        )
        show_response.raise_for_status()
        show = show_response.json()
        tags_response = requests.get(f"{root}/api/tags", timeout=30)
        tags_response.raise_for_status()
        tags = tags_response.json().get("models", [])
        ps_response = requests.get(f"{root}/api/ps", timeout=30)
        ps_response.raise_for_status()
        running = ps_response.json().get("models", [])
        version_response = requests.get(f"{root}/api/version", timeout=30)
        version_response.raise_for_status()
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise GenerationError(f"could not inspect Ollama metadata for {model}: {exc}") from exc

    tag = next(
        (
            item
            for item in tags
            if _same_ollama_tag(str(item.get("name") or item.get("model") or ""), model)
        ),
        None,
    )
    resident = next(
        (
            item
            for item in running
            if _same_ollama_tag(str(item.get("name") or item.get("model") or ""), model)
        ),
        None,
    )
    if tag is None:
        raise GenerationError(f"Ollama tags response omitted installed model {model}")
    if resident is None:
        raise GenerationError(
            f"Ollama ps response omitted {model}; run a generation before recording metadata"
        )
    details = show.get("details") or tag.get("details") or {}
    return ModelMetadata(
        parameter_count=str(details.get("parameter_size") or "").strip(),
        quantization=str(details.get("quantization_level") or "").strip(),
        digest=str(tag.get("digest") or "").strip(),
        family=str(details.get("family") or "").strip(),
        artifact_size_bytes=int(tag.get("size", 0) or 0),
        resident_size_bytes=int(resident.get("size", 0) or 0),
        resident_size_vram_bytes=int(resident.get("size_vram", 0) or 0),
        ollama_version=str(version_response.json().get("version") or "").strip(),
    )


class OllamaGenerator:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        *,
        temperature: float = 0.0,
        top_p: float = 0.95,
        top_k: int = 20,
        seed: int = 42,
        num_ctx: int = 8192,
        max_tokens: int | None = None,
        timeout: int = 600,
    ) -> None:
        self.model = ollama_model_name(model)
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.seed = seed
        self.num_ctx = num_ctx
        self.max_tokens = max_tokens
        self.timeout = timeout

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
            top_k=self.top_k,
            seed=self.seed,
            num_ctx=self.num_ctx,
            fmt=fmt,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
        )
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GenerationError(str(exc)) from exc
        return str(resp.json().get("message", {}).get("content", "")).strip()


__all__ = [
    "GenerationError",
    "OllamaGenerator",
    "ollama_chat_payload",
    "ollama_model_metadata",
    "ollama_model_name",
    "ollama_warm_model",
]
