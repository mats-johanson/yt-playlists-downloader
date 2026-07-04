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
    # ISO-8601 string of when this track was added to its Spotify playlist —
    # the user's actual discovery date, surfaced via Spotify's playlist_items
    # response (`added_at`). Drives Traktor's IMPORT_DATE during the
    # --sync-traktor-dates step so the user can sort their library by their
    # own discovery order in Traktor.
    added_at: str | None = None

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000


@dataclass(frozen=True)
class UnresolvedTrack:
    """Awaiting matcher resolution (Spotify) or already-known YT video (YouTube)."""

    spotify: SpotifyTrackMeta | None = None    # set when source is Spotify
    youtube_video_id: str | None = None        # set when source is YouTube-direct
    youtube_title: str | None = None           # informational, from extract_flat
    # ISO-8601 added-to-playlist timestamp. For Spotify, surfaced via
    # SpotifyTrackMeta.added_at. For YT-direct tracks, synthesized from the
    # video's position in the playlist (later position → later date).
    # Drives Traktor IMPORT_DATE via --sync-traktor-dates.
    added_at: str | None = None

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

    def info_overrides(self) -> dict[str, dict]:
        """Build the per-video `info_dict` override map.

        Maps `{youtube_video_id: {ydl_field: value, ...}}`. Consumed by the
        downloader's metadata postprocessor, which has no provider knowledge —
        this method is the only place Spotify-specific fields get translated
        into yt-dlp's `info_dict` shape.
        """
        out: dict[str, dict] = {}
        for r in self.resolved:
            if not (r.youtube_video_id and r.spotify):
                continue
            meta = r.spotify
            entry: dict = {
                "artist": meta.artist,
                "title": meta.title,
                "album": meta.album,
                "track": meta.title,
            }
            if meta.release_date:
                entry["release_date"] = meta.release_date
                year = meta.release_date.split("-")[0]
                if year.isdigit():
                    entry["release_year"] = int(year)
            out[r.youtube_video_id] = entry
        return out
