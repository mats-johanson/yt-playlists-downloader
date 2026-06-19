"""Persistent cache of Spotify-track → YouTube-video resolutions.

Schema-versioned envelope so format changes don't silently corrupt past data.
Incremental atomic writes so a 429 mid-resolve doesn't lose hours of work.
Stores the FULL SpotifyTrackMeta snapshot per entry, so the next run can
rebuild the metadata-override PP input without re-hitting Spotify.

JSON shape:
{
  "version": 1,
  "entries": {
    "<spotify_track_id>": {
      "video_id": "<youtube_video_id>",
      "match_score": 89.4,
      "match_reason": "matched",
      "spotify": { ... SpotifyTrackMeta ... }
    },
    ...
  }
}
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import threading
from pathlib import Path

from .tracks import ResolvedTrack, SpotifyTrackMeta

SCHEMA_VERSION = 1


class MatchCache:
    """Thread-safe JSON cache with atomic incremental writes."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable — log and start fresh; archived results were
            # never the source of truth for what's on disk anyway.
            return
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return
        entries = data.get("entries", {})
        if isinstance(entries, dict):
            self._entries = entries

    def get(self, spotify_track_id: str) -> ResolvedTrack | None:
        with self._lock:
            entry = self._entries.get(spotify_track_id)
        if not entry:
            return None
        spotify_data = entry.get("spotify")
        spotify = SpotifyTrackMeta(**spotify_data) if spotify_data else None
        return ResolvedTrack(
            youtube_video_id=entry["video_id"],
            spotify=spotify,
            match_score=entry.get("match_score"),
            match_reason=entry.get("match_reason"),
        )

    def put(self, resolved: ResolvedTrack) -> None:
        if not resolved.spotify:
            return
        entry = {
            "video_id": resolved.youtube_video_id,
            "match_score": resolved.match_score,
            "match_reason": resolved.match_reason,
            "spotify": dataclasses.asdict(resolved.spotify),
        }
        with self._lock:
            self._entries[resolved.spotify.spotify_id] = entry
            self._write_atomic()

    def evict(self, spotify_track_id: str) -> None:
        with self._lock:
            self._entries.pop(spotify_track_id, None)
            self._write_atomic()

    def _write_atomic(self) -> None:
        """Write to a sibling tmp file then atomically rename."""
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


import contextlib  # noqa: E402  (used in _write_atomic error path)
