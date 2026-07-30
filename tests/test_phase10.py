"""Phase 10 deterministic polish and reproducibility gates."""

from __future__ import annotations

from pathlib import Path

from vaultledger import __version__
from vaultledger.doctor import run_checks

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_track_a_release_version_and_streamlit_config():
    assert __version__ == "0.1.0"
    config = (REPO_ROOT / ".streamlit" / "config.toml").read_text()
    assert "headless = true" in config
    assert "gatherUsageStats = false" in config


def test_readme_contains_fresh_machine_path_in_order():
    readme = (REPO_ROOT / "README.md").read_text()
    commands = (
        "python3.11 -m venv .venv",
        "make install",
        "ollama pull nomic-embed-text",
        "ollama pull qwen3:8b",
        "make data",
        "make ingest",
        "make doctor",
        "make run",
    )
    positions = [readme.index(command) for command in commands]
    assert positions == sorted(positions)
    assert "synthetic data only" in readme.lower()
    assert "Phase 10" in readme


def test_phase10_entrypoints_and_demo_script_exist():
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "doctor:" in makefile
    assert "verify-track-a:" in makefile
    demo = (REPO_ROOT / "demo" / "README.md").read_text()
    assert "What was Marcus Chen's March closing balance?" in demo
    assert "Data stayed on your machine" in demo


def test_doctor_is_read_only_and_reports_actionable_missing_steps(tmp_path):
    checks = run_checks(tmp_path)
    by_name = {check.name: check for check in checks}
    assert by_name["Python"].passed
    assert by_name["Config"].passed
    assert not by_name["Synthetic corpus"].passed
    assert by_name["Synthetic corpus"].remedy == "Run `make data`."
    assert not by_name["Local indexes"].passed
    assert "make ingest" in by_name["Local indexes"].remedy
    assert not (tmp_path / "data").exists()
