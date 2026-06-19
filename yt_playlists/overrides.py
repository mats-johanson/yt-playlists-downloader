"""Manual Spotify → YouTube overrides.

When the matcher consistently picks the wrong video, the user adds a line to
`config/spotify_overrides.toml`:

    "3n3Ppam7vgaVa1iaRUc9Lp" = "dQw4w9WgXcQ"

The match flow checks overrides BEFORE the cache or matcher. The matcher
itself doesn't know overrides exist — orchestrator wires them in.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


class Overrides:
    def __init__(self, path: Path):
        self._path = path
        self._map: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("rb") as f:
            data = tomllib.load(f)
        # Accept either {track_id: video_id} at top level, or under [tracks].
        if "tracks" in data and isinstance(data["tracks"], dict):
            data = data["tracks"]
        self._map = {
            str(k): str(v)
            for k, v in data.items()
            if isinstance(v, str)
        }

    def get(self, spotify_track_id: str) -> str | None:
        return self._map.get(spotify_track_id)
