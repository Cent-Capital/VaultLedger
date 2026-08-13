"""Prove Phase 18's decoding-config promotion preserves qwen3:8b output bytes.

This deliberately exercises the pre-parity ``/api/generate`` transport twice:
once with Phase 17's implicit top-p/unused seed, then with the now-explicit
``top_p`` and ``seed``. Transport parity is a later Phase 18 change and is not
silently folded into this narrower refactor proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import requests

from vaultledger.config import CONFIG_PATH, REPO_ROOT, load_config
from vaultledger.generate.ollama import ollama_model_name

PROMPT = (
    "Return a JSON object whose only key is `phase` and whose value is the "
    "string `eighteen`. Return no other text."
)
SCHEMA = {
    "type": "object",
    "properties": {"phase": {"type": "string", "const": "eighteen"}},
    "required": ["phase"],
    "additionalProperties": False,
}


def _sha256_bytes(value: str) -> str:
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


def _effective_top_p(parameters: str) -> float:
    for line in parameters.splitlines():
        key, _, value = line.partition(" ")
        if key.strip() == "top_p":
            return float(value.strip())
    raise RuntimeError("Ollama /api/show did not report a top_p model parameter")


def _generate(base_url: str, payload: dict) -> str:
    response = requests.post(f"{base_url}/api/generate", json=payload, timeout=180)
    response.raise_for_status()
    return str(response.json().get("response", ""))


def run(output: Path) -> bool:
    cfg = load_config()
    base_url = cfg.embedding.ollama_url.rstrip("/")
    model = ollama_model_name(cfg.models.T1.id)
    show = requests.post(
        f"{base_url}/api/show", json={"model": model}, timeout=30
    )
    show.raise_for_status()
    show_data = show.json()
    effective_top_p = _effective_top_p(str(show_data.get("parameters", "")))
    if effective_top_p != cfg.generation.top_p:
        raise RuntimeError(
            "typed generation.top_p does not match qwen3:8b's effective "
            f"Ollama model parameter: {cfg.generation.top_p} != {effective_top_p}"
        )

    shared = {
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "think": False,
        "format": SCHEMA,
    }
    legacy_options = {"temperature": cfg.generation.temperature}
    promoted_options = {
        "temperature": cfg.generation.temperature,
        "top_p": cfg.generation.top_p,
        "seed": cfg.seed,
    }
    legacy = _generate(base_url, {**shared, "options": legacy_options})
    promoted = _generate(base_url, {**shared, "options": promoted_options})
    identical = legacy.encode("utf-8") == promoted.encode("utf-8")
    version_response = requests.get(f"{base_url}/api/version", timeout=10)
    version_response.raise_for_status()
    receipt = {
        "receipt": "phase18_decoding_config_promotion_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "config_hash": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        "model": cfg.models.T1.id,
        "ollama_version": version_response.json().get("version"),
        "transport": "/api/generate",
        "scope": (
            "temperature/top_p promotion plus seed plumbing only; the later "
            "generate-to-chat parity correction is outside this proof"
        ),
        "implicit_top_p_source": "installed model parameters from Ollama /api/show",
        "implicit_top_p": effective_top_p,
        "legacy_options": legacy_options,
        "promoted_options": promoted_options,
        "prompt_sha256": _sha256_bytes(PROMPT),
        "legacy_output_sha256": _sha256_bytes(legacy),
        "promoted_output_sha256": _sha256_bytes(promoted),
        "byte_identical": identical,
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
        default=REPO_ROOT / "receipts" / "phase18_decoding_defaults.json",
    )
    args = parser.parse_args()
    return 0 if run(args.output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
