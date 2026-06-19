"""Typed track states.

`UnresolvedTrack` — incoming from a source (Spotify with metadata, or YouTube
                    with a direct video id).
`ResolvedTrack`   — paired with a confirmed YouTube video id, optionally
                    carrying Spotify metadata to override yt-dlp's title parser.
`Unmatched`       — Spotify track the matcher couldn't resolve; logged.

Distinct types so the matcher's signature is
`UnresolvedTrack → ResolvedTrack | Unmatched`. No None-checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpotifyTrackMeta:
    """Spotify-canonical metadata for a track. Drives tag override and matcher."""

    spotify_id: str
    title: str
    artist: str
    album: str
    duration_ms: int
    explicit: bool
    isrc: str | None = None
    release_date: str | None = None   # "YYYY-MM-DD" or "YYYY"

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000


@dataclass(frozen=True)
class UnresolvedTrack:
    """Awaiting matcher resolution (Spotify) or already-known YT video (YouTube)."""

    spotify: SpotifyTrackMeta | None = None    # set when source is Spotify
    youtube_video_id: str | None = None        # set when source is YouTube-direct
    youtube_title: str | None = None           # informational, from extract_flat

    @property
    def is_spotify(self) -> bool:
        return self.spotify is not None

    @property
    def is_youtube_direct(self) -> bool:
        return self.youtube_video_id is not None


@dataclass(frozen=True)
class ResolvedTrack:
    """Bound to a concrete YouTube video. Carries optional Spotify metadata override."""

    youtube_video_id: str
    spotify: SpotifyTrackMeta | None = None    # if from Spotify path
    match_score: float | None = None
    match_reason: str | None = None            # e.g. "override" | "cache" | "matched"


@dataclass(frozen=True)
class Unmatched:
    """Spotify track the matcher couldn't resolve confidently."""

    spotify: SpotifyTrackMeta
    best_candidate_video_id: str | None
    best_score: float
    reason: str


@dataclass
class PlannedFolder:
    """One local folder + everything we plan to (re)download into it.

    folder_name : sanitized title — the actual directory name
    archive_id  : stable identifier embedded in the archive filename so
                  rename of the source playlist doesn't orphan
    resolved    : the tracks we'll hand to yt-dlp
    merge_note  : not None when multiple sources contributed to this folder;
                  surfaced in dashboard / summary
    """

    folder_name: str
    archive_id: str
    resolved: list[ResolvedTrack] = field(default_factory=list)
    unmatched: list[Unmatched] = field(default_factory=list)
    merge_note: str | None = None
