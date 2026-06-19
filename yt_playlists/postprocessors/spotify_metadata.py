"""yt-dlp postprocessor that injects Spotify-canonical metadata into info_dict.

Inserted BEFORE `FFmpegMetadata` so its writes carry through to ID3.
Closes over a `{video_id: SpotifyTrackMeta}` dict supplied at construction.

When the current video isn't in the map, this PP is a no-op — letting yt-dlp's
own field inference (and our existing `MetadataFromField` "Artist - Title"
regex) handle YouTube-only tracks.
"""

from __future__ import annotations

from yt_dlp.postprocessor.common import PostProcessor

from ..tracks import SpotifyTrackMeta


class SpotifyMetadataPP(PostProcessor):
    """Mutates info_dict's artist/title/album/date when we have Spotify truth."""

    def __init__(self, downloader=None, overrides: dict[str, SpotifyTrackMeta] | None = None):
        super().__init__(downloader)
        self._overrides = overrides or {}

    def run(self, info):
        video_id = info.get("id")
        if not video_id:
            return [], info
        meta = self._overrides.get(video_id)
        if not meta:
            return [], info

        info["artist"] = meta.artist
        info["title"] = meta.title
        info["album"] = meta.album
        if meta.release_date:
            info["release_date"] = meta.release_date
            # FFmpegMetadata reads `release_year` for the date tag too.
            year = meta.release_date.split("-")[0]
            if year.isdigit():
                info["release_year"] = int(year)
        info["track"] = meta.title  # FFmpegMetadata writes this to TRACK
        return [], info
