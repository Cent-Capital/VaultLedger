"""Bounded polling watcher for the external Phase 16 inbox."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vaultledger.config import Config, load_config

from .live import LiveIngestResult, ingest_live_pdf


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    mtime_ns: int


class InboxWatcher:
    """Ingest PDFs only after bounded, identical size/mtime observations."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        embed: bool = True,
        graph: bool = True,
        ingest: Callable[..., LiveIngestResult] = ingest_live_pdf,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = config or load_config()
        self.embed = embed
        self.graph = graph
        self._ingest = ingest
        self._sleep = sleep
        self._observations: dict[Path, tuple[FileFingerprint, int]] = {}
        self._state_path = self.cfg.live_paths()["index"] / "watcher_state.json"
        self._processed = self._load_processed()

    def _load_processed(self) -> dict[Path, FileFingerprint]:
        if not self._state_path.exists():
            return {}
        try:
            raw = json.loads(self._state_path.read_text())
            return {
                Path(path): FileFingerprint(
                    size=int(fingerprint["size"]),
                    mtime_ns=int(fingerprint["mtime_ns"]),
                )
                for path, fingerprint in raw.items()
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {}  # corrupt derived state is safely rebuilt from observations

    def _save_processed(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._state_path.with_name(f".{self._state_path.name}.tmp")
        temp.write_text(
            json.dumps(
                {
                    str(path): {"size": fingerprint.size, "mtime_ns": fingerprint.mtime_ns}
                    for path, fingerprint in sorted(
                        self._processed.items(), key=lambda item: str(item[0])
                    )
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temp.replace(self._state_path)

    def poll_once(self) -> list[LiveIngestResult]:
        live_paths = self.cfg.live_paths()  # refuse unsafe config before mkdir/glob
        inbox = live_paths["inbox"]
        inbox.mkdir(parents=True, exist_ok=True)
        current = {
            path
            for path in inbox.iterdir()
            if path.is_file() and path.suffix.casefold() == ".pdf"
        }
        results: list[LiveIngestResult] = []
        for path in sorted(current):
            stat = path.stat()
            fingerprint = FileFingerprint(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
            previous, count = self._observations.get(path, (fingerprint, 0))
            stable_count = count + 1 if previous == fingerprint else 1
            self._observations[path] = (fingerprint, stable_count)
            if stable_count < self.cfg.live.watcher_stable_polls:
                continue
            if self._processed.get(path) == fingerprint:
                continue
            result = self._ingest(
                path,
                self.cfg,
                embed=self.embed,
                graph=self.graph,
            )
            self._processed[path] = fingerprint
            self._save_processed()
            results.append(result)

        removed = set(self._observations) - current
        for path in removed:
            self._observations.pop(path, None)
            if self._processed.pop(path, None) is not None:
                self._save_processed()
        return results

    def watch(self, *, max_polls: int | None = None) -> list[LiveIngestResult]:
        """Poll for a configured finite budget and return every ingest result."""
        budget = max_polls if max_polls is not None else self.cfg.live.watcher_max_polls
        if budget < 1:
            raise ValueError("watcher max_polls must be positive")
        results: list[LiveIngestResult] = []
        for poll in range(budget):
            results.extend(self.poll_once())
            if poll + 1 < budget:
                self._sleep(self.cfg.live.watcher_poll_seconds)
        return results


__all__ = ["FileFingerprint", "InboxWatcher"]
