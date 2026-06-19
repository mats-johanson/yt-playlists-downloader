"""YouTube playlist discovery — direct extraction via yt-dlp."""

from __future__ import annotations

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


class YouTubeSource:
    def __init__(self, urls: list[str]):
        self._urls = urls

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
        tracks = [
            UnresolvedTrack(
                youtube_video_id=e["id"],
                youtube_title=e.get("title"),
            )
            for e in entries
        ]
        return DiscoveredPlaylist(
            folder_name=sanitize_name(title),
            archive_id=f"youtube:{pl_id}",
            source_label=f"youtube:{title}",
            tracks=tracks,
        )
