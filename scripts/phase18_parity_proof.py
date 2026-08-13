"""Live receipt for product/eval Ollama decoding-path parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from vaultledger.config import CONFIG_PATH, REPO_ROOT, load_config
from vaultledger.gateway import LiteLLMGenerator
from vaultledger.generate.ollama import OllamaGenerator

PROMPT = (
    "Return a JSON object whose only key is `path` and whose value is the "
    "string `shared`. Return no other text."
)
SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "const": "shared"}},
    "required": ["path"],
    "additionalProperties": False,
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run(output: Path) -> bool:
    cfg = load_config()
    kwargs = {
        "base_url": cfg.embedding.ollama_url,
        "temperature": cfg.generation.temperature,
        "top_p": cfg.generation.top_p,
        "top_k": cfg.generation.top_k,
        "seed": cfg.seed,
        "num_ctx": cfg.generation.num_ctx,
        "max_tokens": cfg.generation.output_tokens_max,
        "timeout": cfg.generation.request_timeout_seconds,
    }
    product = OllamaGenerator(cfg.models.T1.id, **kwargs)
    matrix = LiteLLMGenerator(cfg.models.T1.id, **kwargs)
    product_output = product.generate_json(PROMPT, SCHEMA)
    matrix_output = matrix.generate_json(PROMPT, SCHEMA)
    identical = product_output.encode("utf-8") == matrix_output.encode("utf-8")
    receipt = {
        "receipt": "phase18_product_eval_parity_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "config_hash": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        "model": cfg.models.T1.id,
        "endpoint": "/api/chat",
        "messages": [{"role": "user", "content_sha256": _sha256(PROMPT)}],
        "options": {
            "temperature": cfg.generation.temperature,
            "top_p": cfg.generation.top_p,
            "top_k": cfg.generation.top_k,
            "seed": cfg.seed,
            "num_ctx": cfg.generation.num_ctx,
            "num_predict": cfg.generation.output_tokens_max,
            "think": False,
        },
        "request_timeout_seconds": cfg.generation.request_timeout_seconds,
        "product_output_sha256": _sha256(product_output),
        "matrix_output_sha256": _sha256(matrix_output),
        "byte_identical": identical,
        "matrix_provider_input_tokens": matrix.snapshot().input_tokens,
        "matrix_provider_output_tokens": matrix.snapshot().output_tokens,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return identical


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "receipts" / "phase18_product_eval_parity.json",
    )
    args = parser.parse_args()
    return 0 if run(args.output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
