"""Provider-agnostic metadata writer — single yt-dlp postprocessor that
produces correct info_dict for ANY track.

Replaces the previous SpotifyMetadataPP + MetadataFromField combo. Their
interaction had a subtle data-corruption race: MetadataFromField runs at
post_process and unconditionally re-parses `info["title"]` against an
"Artist - Title" regex, overwriting fields SpotifyMetadataPP had already
set at pre_process. Empirically observed: 76 of 980 downloaded files had
their `artist` tag re-parsed from a multi-artist Spotify string into the
title's first dash-segment.

Single PP, run at pre_process, replaces the chain:

  Pre-built overrides for this video?  Apply them (artist/title/album/date).
  No overrides?                        Fall back to legacy `Artist - Title` regex.

Provider knowledge stays in `PlannedFolder.info_overrides()` — this module
just consumes a `{video_id: dict[str, value]}` map and copies values into
the info_dict before yt-dlp renders the filename and before FFmpegMetadata
writes ID3 tags. The PP doesn't import SpotifyTrackMeta.
"""

from __future__ import annotations

import re

from yt_dlp.postprocessor.common import PostProcessor

_ARTIST_TITLE_RE = re.compile(r"^(?P<artist>.+?) - (?P<title>.+)$")


class MetadataPP(PostProcessor):
    """Writes canonical artist/title/album into info_dict at pre_process."""

    def __init__(
        self,
        downloader=None,
        overrides: dict[str, dict] | None = None,
    ):
        super().__init__(downloader)
        # overrides: {youtube_video_id: {ydl_field: value}}
        # Values are already in yt-dlp's info_dict shape; we just copy them in.
        self._overrides = overrides or {}

    def run(self, info):
        video_id = info.get("id")
        entry = self._overrides.get(video_id) if video_id else None

        if entry is not None:
            info.update(entry)
        else:
            self._fallback_youtube(info)

        return [], info

    @staticmethod
    def _fallback_youtube(info: dict) -> None:
        """Best-effort split of `Artist - Title` from yt-dlp's title field.

        Only fires when no override is supplied for this video AND info_dict
        doesn't already have an artist (i.e. yt-dlp's extractor didn't expose one).
        """
        if info.get("artist"):
            return
        title = info.get("title", "")
        if not title:
            return
        match = _ARTIST_TITLE_RE.match(title)
        if not match:
            return
        info["artist"] = match.group("artist")
        info["title"] = match.group("title")
