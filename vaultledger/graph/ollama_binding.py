"""Explicit local HTTP bindings for LightRAG.

LightRAG 1.5.6 imports an undeclared ``ollama`` client and attempts to install it
at import time.  VaultLedger does not permit dependency mutation at runtime, so
this module talks to the already-required Ollama HTTP API directly.  It also
pins ``think=false`` for ADR-0007 decoding parity and records local compute
usage without calling zero-dollar inference "free."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp
import numpy as np

from vaultledger.ollama_payload import ollama_chat_payload


@dataclass(frozen=True)
class LocalUsage:
    completion_calls: int = 0
    embedding_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    pricing_status: str = "unpriced"


def _chat_payload(
    *,
    model: str,
    prompt: str,
    system_prompt: str | None,
    history_messages: list[dict[str, str]],
    response_format: Any | None,
    temperature: float,
    top_p: float,
    top_k: int,
    seed: int,
    num_ctx: int,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    fmt = response_format
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        fmt = "json"
    return ollama_chat_payload(
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        seed=seed,
        num_ctx=num_ctx,
        fmt=fmt,
        max_tokens=max_tokens,
    )


class LocalOllamaBinding:
    """Async LightRAG LLM/embedding functions plus an indexing usage receipt."""

    def __init__(
        self,
        *,
        model: str,
        embedding_model: str,
        base_url: str,
        temperature: float = 0.0,
        top_p: float = 0.95,
        top_k: int = 20,
        seed: int = 42,
        num_ctx: int = 8192,
        max_tokens: int | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self.model = model
        self.embedding_model = embedding_model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.seed = seed
        self.num_ctx = num_ctx
        self.max_tokens = max_tokens
        self._completion_calls = 0
        self._embedding_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._latency_ns = 0

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> str:
        payload = _chat_payload(
            model=self.model,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            response_format=kwargs.get("response_format"),
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            seed=self.seed,
            num_ctx=self.num_ctx,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                data = await response.json()
        self._completion_calls += 1
        self._input_tokens += int(data.get("prompt_eval_count", 0) or 0)
        self._output_tokens += int(data.get("eval_count", 0) or 0)
        self._latency_ns += int(data.get("total_duration", 0) or 0)
        return str(data.get("message", {}).get("content", "")).strip()

    async def embed(self, texts: list[str]) -> np.ndarray:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        payload = {"model": self.embedding_model, "input": texts}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.base_url}/api/embed", json=payload) as response:
                response.raise_for_status()
                data = await response.json()
        self._embedding_calls += 1
        self._input_tokens += int(data.get("prompt_eval_count", 0) or 0)
        self._latency_ns += int(data.get("total_duration", 0) or 0)
        return np.asarray(data["embeddings"], dtype=np.float32)

    def usage(self) -> LocalUsage:
        return LocalUsage(
            completion_calls=self._completion_calls,
            embedding_calls=self._embedding_calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            latency_ms=round(self._latency_ns / 1_000_000, 3),
        )


__all__ = ["LocalOllamaBinding", "LocalUsage", "_chat_payload"]
