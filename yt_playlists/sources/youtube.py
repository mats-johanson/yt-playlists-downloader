"""YouTube playlist discovery — direct extraction via yt-dlp."""

from __future__ import annotations

import datetime as _dt

from yt_dlp import YoutubeDL

from ..archive import sanitize_name
from ..tracks import UnresolvedTrack
from . import DiscoveredPlaylist

_SCAN_OPTS = {
    "extract_flat": True,
    "quiet": True,
    "no_warnings": True,
    "force_ipv4": True,
    "skip_download": True,
}


def _synth_added_at(position: int, total: int, today: _dt.date) -> str:
    """Position-based discovery date for YT-only tracks.

    For a playlist of `total` items, the video at `position` (1-based) gets
    `today - (total - position) days`. Tracks added later in the playlist
    (later by user habit — most append to the end) get later dates. Stable
    across runs because each scan re-runs this with the SAME total; only
    `today` shifts.

    DiscoveryDates' merge policy keeps the EARLIEST date seen, so once a
    video has been recorded, this re-derivation can't shift it later.
    """
    days_back = max(total - position, 0)
    d = today - _dt.timedelta(days=days_back)
    return d.isoformat() + "T00:00:00Z"


class YouTubeSource:
    def __init__(self, urls: list[str], *, today: _dt.date | None = None):
        self._urls = urls
        # Injectable for tests so we don't depend on real `date.today()`.
        self._today = today or _dt.date.today()

    def discover(self) -> list[DiscoveredPlaylist]:
        result: list[DiscoveredPlaylist] = []
        for url in self._urls:
            pl = self._scan_one(url)
            if pl is not None:
                result.append(pl)
        return result

    def _scan_one(self, url: str) -> DiscoveredPlaylist | None:
        try:
            with YoutubeDL(_SCAN_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return None
        if not info:
            return None
        title = info.get("title") or "Unknown Playlist"
        pl_id = info.get("id") or url  # fall back to URL as id
        entries = [
            e for e in (info.get("entries") or [])
            if e and e.get("id")
        ]
        if not entries:
            return None
        total = len(entries)
        tracks = [
            UnresolvedTrack(
                youtube_video_id=e["id"],
                youtube_title=e.get("title"),
                added_at=_synth_added_at(position=idx + 1, total=total, today=self._today),
            )
            for idx, e in enumerate(entries)
        ]
        return DiscoveredPlaylist(
            folder_name=sanitize_name(title),
            archive_id=f"youtube:{pl_id}",
            source_label=f"youtube:{title}",
            tracks=tracks,
        )
