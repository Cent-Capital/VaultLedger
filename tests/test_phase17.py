"""Phase 17 packaging and handoff acceptance contracts."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
from pathlib import Path

import pytest

from scripts import launch_vaultledger as launcher
from vaultledger import doctor
from vaultledger.ui_state import sync_sample_question

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_one_click_entrypoint_is_executable_and_finder_friendly():
    entrypoint = REPO_ROOT / "Launch VaultLedger.command"
    assert entrypoint.exists()
    assert os.access(entrypoint, os.X_OK)
    script = entrypoint.read_text()
    assert "python3.11" in script
    assert "scripts/launch_vaultledger.py" in script
    launcher_script = (REPO_ROOT / "scripts" / "launch_vaultledger.py").read_text()
    assert "--server.address=127.0.0.1" in launcher_script
    assert "--server.fileWatcherType=none" in launcher_script


def test_launcher_pins_supported_streamlit_pyarrow_pair():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert '"streamlit>=1.62,<2"' in pyproject
    assert '"pyarrow>=25.0.1,<26"' in pyproject
    assert launcher.LAUNCHER_SCHEMA == "phase17-v3"


def test_busy_default_port_selects_next_port():
    class FakeSocket:
        def bind(self, address):
            if address[1] == launcher.PORT_START:
                raise OSError("occupied")

        def close(self):
            pass

    assert (
        launcher.find_available_port(attempts=2, binder=lambda *args: FakeSocket())
        == launcher.PORT_START + 1
    )


def test_second_click_reuses_verified_running_instance(tmp_path, monkeypatch):
    state = tmp_path / "launcher.json"
    state.write_text(
        json.dumps(
            {
                "pid": 123,
                "port": 8512,
                "repo_root": str(launcher.REPO_ROOT),
            }
        )
    )
    monkeypatch.setattr(launcher, "_pid_is_alive", lambda pid: pid == 123)
    monkeypatch.setattr(launcher, "_url_is_ready", lambda port: port == 8512)
    assert launcher.running_instance(state) == "http://127.0.0.1:8512"
    assert state.exists()


def test_stale_instance_receipt_is_removed(tmp_path, monkeypatch):
    state = tmp_path / "launcher.json"
    state.write_text(
        json.dumps(
            {
                "pid": 123,
                "port": 8501,
                "repo_root": str(launcher.REPO_ROOT),
            }
        )
    )
    monkeypatch.setattr(launcher, "_pid_is_alive", lambda pid: False)
    assert launcher.running_instance(state) is None
    assert not state.exists()


def test_second_click_during_setup_does_not_duplicate_work(tmp_path):
    lock = tmp_path / "launcher.lock"
    lock.write_text(f"{os.getpid()}\n")
    assert launcher._acquire_lock(lock) is False


def test_missing_ollama_opens_official_download_and_stops_readably(monkeypatch):
    opened = []
    monkeypatch.setattr(
        launcher,
        "ollama_model_names",
        lambda: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    with pytest.raises(launcher.LauncherError, match="not installed"):
        launcher.ensure_ollama(opener=opened.append)
    assert opened == [launcher.OLLAMA_DOWNLOAD_URL]


def test_running_ollama_with_models_needs_no_cli_symlink(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "ollama_model_names",
        lambda: {"nomic-embed-text:latest", "qwen3:8b"},
    )
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)

    launcher.ensure_ollama(runner=lambda *args, **kwargs: pytest.fail("CLI invoked"))


def test_running_ollama_without_cli_pulls_missing_model_through_service(monkeypatch):
    pulled = []
    monkeypatch.setattr(
        launcher,
        "ollama_model_names",
        lambda: {"nomic-embed-text:latest"},
    )
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    monkeypatch.setattr(launcher, "_pull_model_via_api", pulled.append)

    launcher.ensure_ollama(runner=lambda *args, **kwargs: pytest.fail("CLI invoked"))

    assert pulled == ["qwen3:8b"]


def test_first_zip_launch_builds_model_free_corpus_with_visible_commands(
    tmp_path, capsys
):
    records_db = tmp_path / "data" / "index" / "records.db"
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "--no-embed":
            records_db.parent.mkdir(parents=True)
            records_db.touch()
        return subprocess.CompletedProcess(command, 0)

    launcher.ensure_synthetic_corpus(
        Path("/private/venv/bin/python"),
        records_db=records_db,
        runner=runner,
    )

    assert [call[0] for call in calls] == [
        ["/private/venv/bin/python", "-m", "vaultledger.synth"],
        ["/private/venv/bin/python", "-m", "vaultledger.ingest", "--no-embed"],
    ]
    assert all(call[1]["cwd"] == launcher.REPO_ROOT for call in calls)
    assert "Creating the 60 sample PDFs" in capsys.readouterr().out


def test_launcher_main_handles_cancel_and_malformed_service_response(monkeypatch, capsys):
    monkeypatch.setattr(
        launcher,
        "launch",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert launcher.main() == 130
    assert "Setup cancelled. Nothing was changed." in capsys.readouterr().out

    monkeypatch.setattr(
        launcher,
        "launch",
        lambda: (_ for _ in ()).throw(ValueError("bad JSON")),
    )
    assert launcher.main() == 1
    assert "VaultLedger could not start: bad JSON" in capsys.readouterr().out


def test_first_run_pulls_only_missing_pinned_models_with_visible_process(monkeypatch):
    monkeypatch.setattr(launcher, "ollama_model_names", lambda: {"nomic-embed-text:latest"})
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    launcher.ensure_ollama(executable="/usr/local/bin/ollama", runner=runner)
    assert [call[0] for call in calls] == [
        ["/usr/local/bin/ollama", "pull", "qwen3:8b"]
    ]
    assert "stdout" not in calls[0][1]


def test_ocr_detection_requires_both_tools_and_is_non_blocking():
    paths = {"ocrmypdf": "/opt/homebrew/bin/ocrmypdf", "tesseract": None}
    status = launcher.detect_ocr_tools(paths.get)
    assert not status.available
    assert status.missing == ("tesseract",)


def test_measured_example_selection_updates_but_custom_question_survives_rerun():
    questions = {
        "Marcus": "What was Marcus's balance?",
        "Unanswerable": "What is Marcus's credit score?",
        "Custom": "",
    }
    state = {}
    sync_sample_question(
        state,
        corpus="Synthetic evaluation corpus",
        sample="Marcus",
        questions=questions,
    )
    assert state["question_input"] == "What was Marcus's balance?"

    sync_sample_question(
        state,
        corpus="Synthetic evaluation corpus",
        sample="Unanswerable",
        questions=questions,
    )
    assert state["question_input"] == "What is Marcus's credit score?"

    state["question_input"] = "My edited question"
    sync_sample_question(
        state,
        corpus="Synthetic evaluation corpus",
        sample="Unanswerable",
        questions=questions,
    )
    assert state["question_input"] == "My edited question"


def test_doctor_marks_missing_ocr_as_optional_and_explains_the_cost(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    check = doctor._ocr_check()
    assert not check.passed
    assert not check.required
    assert "text PDFs still work" in check.detail
    assert "brew install ocrmypdf" in check.remedy


def test_phase17_handoff_artifacts_and_truthful_boundaries_exist():
    readme = (REPO_ROOT / "README.md").read_text()
    assert "Launch VaultLedger.command" in readme
    assert "5.2 GB" in readme
    assert "Scanned PDFs" in readme
    assert "No independent non-technical reader" in readme
    assert (REPO_ROOT / "receipts" / "phase17_clean_install.md").exists()
    assert (REPO_ROOT / "demo" / "vaultledger_phase17_demo.mp4").exists()
