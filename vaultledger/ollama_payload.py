"""Dependency-free native Ollama request construction.

This module deliberately lives outside ``vaultledger.generate`` so low-level
graph and retrieval adapters can share the product payload without importing the
generation package and closing a retrieve/generate import cycle.
"""

from __future__ import annotations


def ollama_model_name(model_id: str) -> str:
    """Convert config model ids like ``ollama/qwen3:8b`` to Ollama names."""
    return model_id.removeprefix("ollama/")


def ollama_chat_payload(
    *,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    top_k: int,
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
            "top_k": top_k,
            "seed": seed,
            "num_ctx": num_ctx,
        },
    }
    if fmt is not None:
        payload["format"] = fmt
    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens
    return payload


__all__ = ["ollama_chat_payload", "ollama_model_name"]
