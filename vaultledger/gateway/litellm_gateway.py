"""LiteLLM-backed generation gateway with per-call usage receipts.

The rest of VaultLedger depends only on ``generate_json``.  This adapter keeps
that stable protocol while normalising provider response metadata for the
Phase 11 matrix.  LiteLLM is imported lazily so deterministic tests and the
local-only app do not probe a provider merely by importing the package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import requests

from vaultledger.generate.ollama import GenerationError, ollama_model_name


@dataclass(frozen=True)
class GatewayCall:
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    token_source: str
    pricing_status: str


@dataclass(frozen=True)
class GatewayTotals:
    calls: int
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float

    def delta(self, earlier: GatewayTotals) -> GatewayTotals:
        return GatewayTotals(
            calls=self.calls - earlier.calls,
            latency_ms=round(self.latency_ms - earlier.latency_ms, 3),
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            cost_usd=round(self.cost_usd - earlier.cost_usd, 10),
        )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _content(response: Any) -> str:
    choices = _field(response, "choices", [])
    if not choices:
        raise GenerationError("LiteLLM returned no completion choices")
    message = _field(choices[0], "message", {})
    content = _field(message, "content", "")
    if content is None:
        return ""
    return str(content).strip()


class LiteLLMGenerator:
    """Structured generator implementing VaultLedger's stable gateway seam."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434",
        timeout: int = 180,
        temperature: float = 0.0,
        top_p: float = 0.95,
        seed: int = 42,
        completion_fn: Callable[..., Any] | None = None,
        cost_fn: Callable[..., float] | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self._completion_fn = completion_fn
        self._cost_fn = cost_fn
        self.calls: list[GatewayCall] = []

    def _functions(self) -> tuple[Callable[..., Any], Callable[..., float] | None]:
        if self._completion_fn is not None:
            return self._completion_fn, self._cost_fn
        try:
            from litellm import completion, completion_cost
        except ImportError as exc:  # pragma: no cover - exercised by the CLI environment
            raise GenerationError(
                "LiteLLM is not installed; run `make install` or install `.[gateway]`."
            ) from exc
        return completion, completion_cost

    def is_available(self) -> bool:
        """Check that the configured local Ollama tag is present."""
        if not self.model.startswith("ollama/"):
            return True
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            response.raise_for_status()
            names = [str(item.get("name", "")) for item in response.json().get("models", [])]
        except (requests.RequestException, ValueError, TypeError):
            return False
        expected = ollama_model_name(self.model)
        return any(name == expected or name.startswith(f"{expected}:") for name in names)

    def snapshot(self) -> GatewayTotals:
        return GatewayTotals(
            calls=len(self.calls),
            latency_ms=round(sum(call.latency_ms for call in self.calls), 3),
            input_tokens=sum(call.input_tokens for call in self.calls),
            output_tokens=sum(call.output_tokens for call in self.calls),
            cost_usd=round(sum(call.cost_usd for call in self.calls), 10),
        )

    def generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        completion_fn, cost_fn = self._functions()
        started = perf_counter()
        try:
            request = dict(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_base=self.base_url,
                temperature=self.temperature if temperature is None else temperature,
                top_p=self.top_p,
                seed=self.seed,
                # Qwen 3 defaults to thinking in Ollama. With a constrained
                # schema that can spend the entire output on hidden reasoning
                # and return empty content, so matrix generation explicitly
                # disables thinking for comparable answer budgets.
                think=False,
                timeout=self.timeout,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "vaultledger_answer",
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
            if max_tokens is not None:
                request["max_tokens"] = max_tokens
            response = completion_fn(**request)
        except Exception as exc:
            # LiteLLM exposes provider-specific exception classes.  The gateway
            # deliberately translates all of them into the product's stable
            # error so routing and matrix code remain provider-independent.
            raise GenerationError(f"LiteLLM completion failed for {self.model}: {exc}") from exc

        latency_ms = round((perf_counter() - started) * 1000, 3)
        usage = _field(response, "usage", {}) or {}
        input_tokens = int(_field(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(_field(usage, "completion_tokens", 0) or 0)
        token_source = "provider_usage" if input_tokens or output_tokens else "unavailable"

        hidden = _field(response, "_hidden_params", {}) or {}
        raw_cost = _field(hidden, "response_cost", None)
        if raw_cost is None and cost_fn is not None:
            try:
                raw_cost = cost_fn(completion_response=response)
            except Exception:
                raw_cost = None
        pricing_status = "priced" if raw_cost not in (None, 0, 0.0) else "unpriced"
        cost_usd = float(raw_cost or 0.0)
        self.calls.append(
            GatewayCall(
                model=self.model,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                token_source=token_source,
                pricing_status=pricing_status,
            )
        )
        return _content(response)


__all__ = ["GatewayCall", "GatewayTotals", "LiteLLMGenerator"]
