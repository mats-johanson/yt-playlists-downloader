"""Source layer — anything that yields tracks to download.

The `Source` Protocol is intentionally narrow. Spotify and YouTube each fan out
into a list of *playlists*, each carrying its own tracks. The pipeline groups
them by sanitized folder name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..tracks import UnresolvedTrack


@dataclass(frozen=True)
class DiscoveredPlaylist:
    """One playlist's worth of tracks, plus its folder identity."""

    folder_name: str        # sanitized title — what the directory ends up named
    archive_id: str         # stable id (Spotify playlist id, or YouTube playlist id)
    source_label: str       # e.g. "spotify:My Playlist", "youtube:<url>"
    tracks: list[UnresolvedTrack]


class Source(Protocol):
    def discover(self) -> list[DiscoveredPlaylist]: ...
