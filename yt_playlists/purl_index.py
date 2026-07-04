"""Persistent `{mp3_path: youtube_video_id}` cache.

Cuts the cost of the Traktor sync step. Without it, every sync re-walks every
MP3 with ffprobe to extract its `purl` ID3 tag — ~3 minutes for 1000+ files.
With it, the sync uses the cached video_id and only ffprobes paths it hasn't
seen yet (new downloads). Stable across runs because:

- a file's `purl` tag never changes (it points at the source YT video and we
  always re-tag from the same source)
- a file's CONTENT can be replaced (re-download to fix a corruption), but the
  purl stays the same source — cache stays valid
- a file's PATH never changes within a run (yt-dlp writes to the final dest,
  no relocation)

Stale entries (file gone from disk) are pruned on demand by `prune_missing`.

Schema-versioned envelope, same pattern as DiscoveryDates / MatchCache.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path

SCHEMA_VERSION = 1


class PurlIndex:
    """Thread-safe persistent map of `{mp3_path: video_id}`."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._entries: dict[str, str] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return
        entries = data.get("entries", {})
        if isinstance(entries, dict):
            self._entries = entries

    def get(self, mp3_path: str) -> str | None:
        with self._lock:
            return self._entries.get(mp3_path)

    def set(self, mp3_path: str, video_id: str) -> None:
        if not mp3_path or not video_id:
            return
        with self._lock:
            if self._entries.get(mp3_path) == video_id:
                return
            self._entries[mp3_path] = video_id
            self._dirty = True

    def prune_missing(self) -> int:
        """Drop entries whose path no longer exists on disk. Returns count removed."""
        with self._lock:
            gone = [p for p in self._entries if not Path(p).exists()]
            for p in gone:
                del self._entries[p]
            if gone:
                self._dirty = True
        return len(gone)

    def flush(self) -> None:
        """Write to disk if dirty. Call at the end of an operation."""
        with self._lock:
            if not self._dirty:
                return
            self._write_atomic()
            self._dirty = False

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _write_atomic(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": SCHEMA_VERSION, "entries": self._entries}
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_name, self._path)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise
