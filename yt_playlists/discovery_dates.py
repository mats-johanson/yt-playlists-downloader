"""Persistent map of `youtube_video_id → user-discovery date`.

Powers the `--sync-traktor-dates` feature: sort Traktor's Imported column
by the date the USER added the track to their playlist (not the date
Traktor first scanned the MP3).

Two sources contribute:

- **Spotify**: each playlist_item response includes `added_at` (ISO-8601 of
  exactly when the user added the track to that playlist). We capture it
  during discovery and persist by `youtube_video_id` after resolve.
- **YouTube**: yt-dlp's extract_flat doesn't surface a true "added-to-playlist"
  date for user playlists, so we synthesize one from `playlist_index`:
  for a playlist scanned today with N items, the video at position k gets
  `today - (N - k) days`. Tracks added later in the playlist (later by
  user habit, since most people append) get later dates.

Merge policy: when a video appears via multiple playlists or multiple runs,
keep the EARLIEST date seen — that matches "when did I FIRST discover this
track". Updates are idempotent; re-running doesn't shift existing entries
into the future.

Schema-versioned JSON envelope so format changes don't silently corrupt
past data; same pattern as match_cache.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path

SCHEMA_VERSION = 1


class DiscoveryDates:
    """Thread-safe persistent map keyed by YouTube video id."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        # {video_id: {"added_at": ISO, "source_playlist": str}}
        self._entries: dict[str, dict] = {}
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

    def get(self, video_id: str) -> str | None:
        with self._lock:
            entry = self._entries.get(video_id)
        return entry.get("added_at") if entry else None

    def record(self, video_id: str, added_at: str, source_playlist: str) -> None:
        """Record an `added_at` for a video.

        Merge rule: keep the EARLIEST date seen. ISO-8601 strings sort
        lexicographically, so a plain string compare suffices for that.
        """
        if not video_id or not added_at:
            return
        with self._lock:
            existing = self._entries.get(video_id)
            if existing is None or added_at < existing.get("added_at", "9999"):
                self._entries[video_id] = {
                    "added_at": added_at,
                    "source_playlist": source_playlist,
                }
                self._write_atomic()

    def record_many(self, items: list[tuple[str, str, str]]) -> int:
        """Batch record (video_id, added_at, source_playlist) tuples.

        Single atomic write at the end — much cheaper than per-call.
        Returns the count of entries that changed (newly added or overwritten
        by an earlier date).
        """
        changed = 0
        with self._lock:
            for video_id, added_at, source_playlist in items:
                if not video_id or not added_at:
                    continue
                existing = self._entries.get(video_id)
                if existing is None or added_at < existing.get("added_at", "9999"):
                    self._entries[video_id] = {
                        "added_at": added_at,
                        "source_playlist": source_playlist,
                    }
                    changed += 1
            if changed:
                self._write_atomic()
        return changed

    def all(self) -> dict[str, str]:
        with self._lock:
            return {vid: entry["added_at"] for vid, entry in self._entries.items()}

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
