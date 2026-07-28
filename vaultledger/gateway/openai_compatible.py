"""Small OpenAI-compatible cloud client for routing v1.

Phase 11 replaces this single-provider seam with LiteLLM. Keeping the client
here prevents cloud imports or availability probes on the local-only path.
"""

from __future__ import annotations

import requests

from vaultledger.generate.ollama import GenerationError


class OpenAICompatibleGenerator:
    def __init__(self, model: str, base_url: str, api_key: str, timeout: int = 180) -> None:
        if not base_url or not api_key:
            raise GenerationError("cloud endpoint or API key is not configured")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def generate_json(
        self, prompt: str, schema: dict, *, temperature: float = 0.0
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "vaultledger_answer", "schema": schema},
            },
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
        except (requests.RequestException, KeyError, IndexError, TypeError) as exc:
            raise GenerationError(f"cloud generation failed: {exc}") from exc


__all__ = ["OpenAICompatibleGenerator"]
