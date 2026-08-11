#!/usr/bin/env python3
"""Visible, bounded macOS first-run setup and Streamlit launcher.

This file intentionally uses only the Python standard library.  It must be able
to explain or repair a missing project environment before VaultLedger itself is
importable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INSTALL_MARKER = VENV_DIR / ".vaultledger-install"
STATE_DIR = Path.home() / "Library" / "Application Support" / "VaultLedger"
STATE_FILE = STATE_DIR / "launcher.json"
LOCK_FILE = STATE_DIR / "launcher.lock"

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/mac"
REQUIRED_MODELS = ("nomic-embed-text", "qwen3:8b")
PORT_START = 8501
PORT_ATTEMPTS = 20
OLLAMA_START_ATTEMPTS = 30
SERVER_START_ATTEMPTS = 60
LAUNCHER_SCHEMA = "phase17-v2"


class LauncherError(RuntimeError):
    """A setup problem that should be shown without a traceback."""


@dataclass(frozen=True)
class OcrStatus:
    """Optional scanned-document capability detected on PATH."""

    ocrmypdf: str | None
    tesseract: str | None

    @property
    def available(self) -> bool:
        return bool(self.ocrmypdf and self.tesseract)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, path in (("ocrmypdf", self.ocrmypdf), ("tesseract", self.tesseract))
            if not path
        )


def _heading(message: str) -> None:
    print(f"\n== {message} ==", flush=True)


def _install_fingerprint() -> str:
    digest = hashlib.sha256()
    digest.update(LAUNCHER_SCHEMA.encode())
    digest.update(PYPROJECT.read_bytes())
    return digest.hexdigest()


def _environment_ready(
    python: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    if not python.is_file():
        return False
    probe = (
        "from importlib.metadata import version; "
        "from packaging.version import Version; "
        "import aiohttp, chromadb, lightrag, pdfplumber, presidio_analyzer, "
        "rank_bm25, sentence_transformers, spacy, streamlit; "
        "assert Version(version('streamlit')) >= Version('1.61'); "
        "assert Version(version('pyarrow')) < Version('25'); "
        "spacy.load('en_core_web_sm')"
    )
    try:
        result = runner(
            [str(python), "-c", probe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def ensure_environment(
    *,
    host_python: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    """Create the private environment and visibly install runtime dependencies."""

    host = host_python or Path(sys.executable)
    if sys.version_info < (3, 11):  # noqa: UP036 - this bootstrap may run outside the package
        raise LauncherError(
            "VaultLedger needs Python 3.11 or newer. Install current Python from "
            "https://www.python.org/downloads/macos/ and double-click the launcher again."
        )
    if VENV_DIR.exists() and not VENV_PYTHON.is_file():
        raise LauncherError(
            f"The environment at {VENV_DIR} is incomplete. Move that folder to the Trash "
            "and double-click the launcher again."
        )
    if not VENV_PYTHON.is_file():
        _heading("Preparing VaultLedger (first launch only)")
        print("Creating a private Python environment…", flush=True)
        runner([str(host), "-m", "venv", str(VENV_DIR)], check=True)

    wanted = _install_fingerprint()
    installed = INSTALL_MARKER.read_text().strip() if INSTALL_MARKER.exists() else ""
    if installed != wanted or not _environment_ready(VENV_PYTHON, runner):
        print(
            "Installing local app components. Progress will remain visible; this can take "
            "several minutes on the first launch.",
            flush=True,
        )
        runner(
            [
                str(VENV_PYTHON),
                "-m",
                "pip",
                "install",
                "-e",
                f"{REPO_ROOT}[rerank,gateway,graph]",
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        runner(
            [str(VENV_PYTHON), "-m", "spacy", "download", "en_core_web_sm"],
            cwd=REPO_ROOT,
            check=True,
        )
        if not _environment_ready(VENV_PYTHON, runner):
            raise LauncherError("The Python install finished but its readiness check failed.")
        INSTALL_MARKER.write_text(wanted + "\n")
    else:
        print("Local app components are ready.", flush=True)
    return VENV_PYTHON


def _json_url(url: str, *, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - loopback only
        return json.loads(response.read())


def ollama_model_names() -> set[str]:
    payload = _json_url(f"{OLLAMA_URL}/api/tags")
    return {str(model.get("name", "")) for model in payload.get("models", [])}


def _has_model(names: set[str], wanted: str) -> bool:
    return wanted in names or f"{wanted}:latest" in names


def _wait_for_ollama(*, sleep: Callable[[float], None] = time.sleep) -> bool:
    for attempt in range(OLLAMA_START_ATTEMPTS):
        try:
            ollama_model_names()
            print("Ollama is ready.", flush=True)
            return True
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 < OLLAMA_START_ATTEMPTS:
                print("Waiting for Ollama…", flush=True)
                sleep(2)
    return False


def ensure_ollama(
    *,
    executable: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    opener: Callable[[str], object] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Start Ollama if needed and visibly pull the two product-path models."""

    command = executable or shutil.which("ollama")
    if not command:
        opener(OLLAMA_DOWNLOAD_URL)
        raise LauncherError(
            "Ollama is not installed. Its official macOS download page is open. Install "
            "Ollama, open it once, then double-click Launch VaultLedger again."
        )

    try:
        names = ollama_model_names()
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        _heading("Starting the local AI service")
        if sys.platform == "darwin" and Path("/Applications/Ollama.app").exists():
            runner(["/usr/bin/open", "-gja", "Ollama"], check=False)
        else:
            subprocess.Popen(
                [command, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        if not _wait_for_ollama(sleep=sleep):
            raise LauncherError(
                "Ollama did not become ready within one minute. Open the Ollama app, wait "
                "for it to finish starting, then launch VaultLedger again."
            ) from None
        names = ollama_model_names()

    missing = [model for model in REQUIRED_MODELS if not _has_model(names, model)]
    if missing:
        _heading("Downloading the local AI models")
        print(
            "The progress below is live. qwen3:8b is about 5.2 GB and "
            "nomic-embed-text is about 0.3 GB.",
            flush=True,
        )
    for model in missing:
        print(f"\nDownloading {model}…", flush=True)
        result = runner([command, "pull", model], check=False)
        if result.returncode != 0:
            raise LauncherError(
                f"Ollama could not download {model}. Check the internet connection and free "
                "disk space, then launch VaultLedger again."
            )


def detect_ocr_tools(which: Callable[[str], str | None] = shutil.which) -> OcrStatus:
    """Return the optional OCR executables without installing or invoking them."""

    return OcrStatus(ocrmypdf=which("ocrmypdf"), tesseract=which("tesseract"))


def explain_ocr(status: OcrStatus) -> None:
    _heading("Document support")
    if status.available:
        print("Text PDFs and scanned PDFs are supported (OCR tools found).", flush=True)
    else:
        print(
            "Text PDFs are ready. Scanned PDFs are NOT available because "
            f"{', '.join(status.missing)} is missing. VaultLedger will reject a scan with a "
            "clear message instead of silently indexing an empty document.",
            flush=True,
        )
        print("Optional fix: install Homebrew, then run: brew install ocrmypdf", flush=True)


def prepare_default_inbox() -> Path:
    """Create the documented external drop folder, never a path in the checkout."""

    inbox = (Path.home() / "VaultLedger" / "Inbox").resolve()
    if inbox == REPO_ROOT.resolve() or inbox.is_relative_to(REPO_ROOT.resolve()):
        raise LauncherError(f"Refusing to create a user-document folder in the repository: {inbox}")
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def find_available_port(
    start: int = PORT_START,
    attempts: int = PORT_ATTEMPTS,
    *,
    binder: Callable[..., socket.socket] = socket.socket,
) -> int:
    """Find a loopback port in a bounded range; never steal an occupied port."""

    for port in range(start, start + attempts):
        sock = binder(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()
    raise LauncherError(
        f"Ports {start}–{start + attempts - 1} are busy. Close another local app and try again."
    )


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/_stcore/health"


def _url_is_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(_health_url(port), timeout=1) as response:  # noqa: S310
            return response.status == 200
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def running_instance(state_file: Path = STATE_FILE) -> str | None:
    """Return a verified prior instance URL, discarding only its stale receipt."""

    if not state_file.exists():
        return None
    try:
        state = json.loads(state_file.read_text())
        pid = int(state["pid"])
        port = int(state["port"])
        same_repo = Path(state["repo_root"]).resolve() == REPO_ROOT.resolve()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        state_file.unlink(missing_ok=True)
        return None
    if same_repo and _pid_is_alive(pid) and _url_is_ready(port):
        return f"http://127.0.0.1:{port}"
    state_file.unlink(missing_ok=True)
    return None


def _acquire_lock(lock_file: Path = LOCK_FILE) -> bool:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            owner = int(lock_file.read_text().strip())
        except (OSError, ValueError):
            owner = -1
        if _pid_is_alive(owner):
            return False
        lock_file.unlink(missing_ok=True)
        descriptor = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(f"{os.getpid()}\n")
    return True


def _write_state(pid: int, port: int, state_file: Path = STATE_FILE) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp = state_file.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {"pid": pid, "port": port, "repo_root": str(REPO_ROOT)},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temp.replace(state_file)


def start_streamlit(
    python: Path,
    port: int,
    *,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
) -> subprocess.Popen:
    """Start Streamlit and require its real health endpoint before returning."""

    process = popen(
        [
            str(python),
            "-m",
            "streamlit",
            "run",
            str(REPO_ROOT / "app" / "streamlit_app.py"),
            "--server.headless=true",
            "--server.address=127.0.0.1",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
            f"--server.port={port}",
        ],
        cwd=REPO_ROOT,
    )
    for attempt in range(SERVER_START_ATTEMPTS):
        if process.poll() is not None:
            raise LauncherError(
                f"VaultLedger stopped during startup (exit code {process.returncode})."
            )
        if _url_is_ready(port):
            return process
        if attempt + 1 < SERVER_START_ATTEMPTS:
            sleep(1)
    process.terminate()
    raise LauncherError("VaultLedger did not become ready within one minute.")


def launch(*, opener: Callable[[str], object] = webbrowser.open) -> int:
    """Prepare dependencies, start one server, and open its browser page."""

    existing = running_instance()
    if existing:
        print(f"VaultLedger is already running at {existing}", flush=True)
        opener(existing)
        return 0
    if not _acquire_lock():
        print(
            "VaultLedger setup is already running in another window. Keep that first window "
            "open; it will open the browser when setup finishes.",
            flush=True,
        )
        return 0

    process: subprocess.Popen | None = None
    try:
        existing = running_instance()
        if existing:
            opener(existing)
            return 0
        python = ensure_environment()
        ensure_ollama()
        explain_ocr(detect_ocr_tools())
        inbox = prepare_default_inbox()
        print(f"Your private PDF drop folder is ready at: {inbox}", flush=True)
        port = find_available_port()
        if port != PORT_START:
            print(f"Port {PORT_START} is busy; using {port} instead.", flush=True)
        _heading("Opening VaultLedger")
        process = start_streamlit(python, port)
        _write_state(process.pid, port)
    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()
        raise
    finally:
        LOCK_FILE.unlink(missing_ok=True)

    url = f"http://127.0.0.1:{port}"
    print(f"VaultLedger is ready at {url}", flush=True)
    print("Keep this window open while you use VaultLedger.", flush=True)
    opener(url)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return process.wait()
    finally:
        try:
            state = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            state = {}
        if state.get("pid") == process.pid:
            STATE_FILE.unlink(missing_ok=True)


def main() -> int:
    try:
        return launch()
    except (
        LauncherError,
        OSError,
        subprocess.CalledProcessError,
        urllib.error.URLError,
    ) as exc:
        print(f"\nVaultLedger could not start: {exc}", flush=True)
        print("No user document was changed.", flush=True)
        if sys.stdin.isatty():
            input("\nPress Return to close this window…")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
