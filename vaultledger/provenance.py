"""Shared provenance helpers for manifests, receipts, and generated reports."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from vaultledger.config import CONFIG_PATH, REPO_ROOT


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest for ``value``."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash UTF-8 text using the repository's canonical encoding."""
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    """Hash one file without duplicating receipt-specific boilerplate."""
    return sha256_bytes(Path(path).read_bytes())


def git_output(*args: str, repo_root: str | Path = REPO_ROOT) -> str:
    """Run a read-only Git command and return stripped standard output."""
    result = subprocess.run(
        ["git", *args],
        cwd=Path(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_sha(
    repo_root: str | Path = REPO_ROOT,
    *,
    fallback: str = "unknown",
) -> str:
    """Return ``HEAD`` while preserving the runtime manifest fallback contract."""
    try:
        return git_output("rev-parse", "HEAD", repo_root=repo_root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return fallback


def config_hash(path: str | Path = CONFIG_PATH) -> str:
    """Return the content hash used by every manifest and receipt."""
    return sha256_file(path)


__all__ = [
    "config_hash",
    "git_output",
    "git_sha",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
]
