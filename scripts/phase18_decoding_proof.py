"""Check Phase 18's decoding defaults against qwen3:8b and confirm output bytes.

This deliberately exercises the pre-parity ``/api/generate`` transport twice:
once with Phase 17's implicit top-p/unused seed, then with the now-explicit
``top_p``, ``top_k`` and ``seed``. The byte comparison is confirmatory rather
than discriminating because temperature zero is greedy and the schema has one
valid value. The fail-loud ``/api/show`` parameter checks justify the promoted
values. Transport parity is a later Phase 18 change.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import requests

from vaultledger.config import load_config
from vaultledger.generate.ollama import ollama_model_name
from vaultledger.provenance import config_hash, git_output, sha256_text

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


def _effective_parameter(parameters: str, name: str) -> float:
    for line in parameters.splitlines():
        key, _, value = line.partition(" ")
        if key.strip() == name:
            return float(value.strip())
    raise RuntimeError(f"Ollama /api/show did not report a {name} model parameter")


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
    parameters = str(show_data.get("parameters", ""))
    effective_top_p = _effective_parameter(parameters, "top_p")
    effective_top_k = int(_effective_parameter(parameters, "top_k"))
    if effective_top_p != cfg.generation.top_p:
        raise RuntimeError(
            "typed generation.top_p does not match qwen3:8b's effective "
            f"Ollama model parameter: {cfg.generation.top_p} != {effective_top_p}"
        )
    if effective_top_k != cfg.generation.top_k:
        raise RuntimeError(
            "typed generation.top_k does not match qwen3:8b's effective "
            f"Ollama model parameter: {cfg.generation.top_k} != {effective_top_k}"
        )
    if cfg.generation.temperature != 0.0:
        raise RuntimeError("decoding-default confirmation requires greedy temperature=0.0")

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
        "top_k": cfg.generation.top_k,
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
        "git_sha": git_output("rev-parse", "HEAD"),
        "config_hash": config_hash(),
        "model": cfg.models.T1.id,
        "ollama_version": version_response.json().get("version"),
        "transport": "/api/generate",
        "scope": (
            "temperature/top_p/top_k promotion plus seed plumbing only; the later "
            "generate-to-chat parity correction is outside this proof"
        ),
        "interpretation": (
            "confirmatory only: temperature zero is greedy and the const schema "
            "admits one value; /api/show checks justify the promoted parameter values"
        ),
        "byte_identity_discriminating": False,
        "implicit_top_p_source": "installed model parameters from Ollama /api/show",
        "implicit_top_p": effective_top_p,
        "implicit_top_k_source": "installed model parameters from Ollama /api/show",
        "implicit_top_k": effective_top_k,
        "legacy_options": legacy_options,
        "promoted_options": promoted_options,
        "prompt_sha256": sha256_text(PROMPT),
        "legacy_output_sha256": sha256_text(legacy),
        "promoted_output_sha256": sha256_text(promoted),
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
