"""Regression tests for the unified MetadataPP and PlannedFolder.info_overrides.

The pre-fix design had a SpotifyMetadataPP at pre_process + a MetadataFromField
at post_process. The post_process pass unconditionally re-parsed `info["title"]`
against `^(Artist) - (Title)$` and overwrote both fields — silently corrupting
multi-artist tracks where the Spotify-canonical title contained ` - ` (e.g.
"If Only I Could - Liem Remix" → artist became "If Only I Could").

MetadataPP merges both responsibilities into one pre_process PP, eliminating
the race. Provider-specific translation (SpotifyTrackMeta → yt-dlp info_dict
shape) happens in PlannedFolder.info_overrides(), keeping MetadataPP and the
downloader truly provider-agnostic.

These tests pin both behaviors so neither regression can return.
"""

from yt_playlists.postprocessors.spotify_metadata import MetadataPP
from yt_playlists.tracks import PlannedFolder, ResolvedTrack, SpotifyTrackMeta


def _meta(**kw) -> SpotifyTrackMeta:
    base = dict(
        spotify_id="sp1",
        title="Default Title",
        artist="Default Artist",
        album="Default Album",
        duration_ms=200_000,
        explicit=False,
        release_date="2024-01-01",
    )
    base.update(kw)
    return SpotifyTrackMeta(**base)


# --- MetadataPP (generic) ---


def test_overrides_overwrite_artist_title_album():
    overrides = {"abc123": {
        "artist": "Real Artist", "title": "Real Title",
        "album": "Real Album", "track": "Real Title",
    }}
    pp = MetadataPP(overrides=overrides)
    info = {"id": "abc123", "title": "Garbage YT Title", "artist": "Garbage Channel"}
    _, out = pp.run(info)
    assert out["artist"] == "Real Artist"
    assert out["title"] == "Real Title"
    assert out["album"] == "Real Album"
    assert out["track"] == "Real Title"


def test_dash_in_title_preserved_when_overridden():
    """The original re-stomp bug. Override values applied verbatim — no regex parsing."""
    overrides = {"vid": {
        "title": "If Only I Could - Liem Remix",
        "artist": "Fusion Groove Orchestra, Steve Lucas, Liem",
    }}
    pp = MetadataPP(overrides=overrides)
    info = {"id": "vid", "title": "Original YT Title", "artist": "Channel"}
    _, out = pp.run(info)
    assert out["title"] == "If Only I Could - Liem Remix"
    assert out["artist"] == "Fusion Groove Orchestra, Steve Lucas, Liem"


def test_no_override_falls_back_to_artist_title_regex():
    pp = MetadataPP(overrides={})
    info = {"id": "vid", "title": "Some Band - Some Song"}
    _, out = pp.run(info)
    assert out["artist"] == "Some Band"
    assert out["title"] == "Some Song"


def test_fallback_skips_when_artist_already_present():
    """If yt-dlp's extractor populated `artist`, don't second-guess it."""
    pp = MetadataPP(overrides={})
    info = {"id": "vid", "title": "Some Band - Some Song", "artist": "Pre-set Artist"}
    _, out = pp.run(info)
    assert out["artist"] == "Pre-set Artist"
    assert out["title"] == "Some Band - Some Song"


def test_fallback_no_dash_left_alone():
    pp = MetadataPP(overrides={})
    info = {"id": "vid", "title": "JustTitle"}
    _, out = pp.run(info)
    assert "artist" not in out
    assert out["title"] == "JustTitle"


# --- PlannedFolder.info_overrides (Spotify → dict translation) ---


def test_planned_folder_info_overrides_flattens_spotify_meta():
    folder = PlannedFolder(
        folder_name="Cool",
        archive_id="cool-id",
        resolved=[
            ResolvedTrack(
                youtube_video_id="v1",
                spotify=_meta(title="Glue", artist="Bicep", album="Bicep"),
            ),
            ResolvedTrack(
                youtube_video_id="v2",
                spotify=_meta(release_date="2018"),
            ),
        ],
    )
    overrides = folder.info_overrides()
    assert overrides["v1"]["title"] == "Glue"
    assert overrides["v1"]["artist"] == "Bicep"
    assert overrides["v1"]["album"] == "Bicep"
    assert overrides["v1"]["track"] == "Glue"
    assert overrides["v1"]["release_date"] == "2024-01-01"
    assert overrides["v1"]["release_year"] == 2024
    assert overrides["v2"]["release_year"] == 2018


def test_planned_folder_info_overrides_skips_youtube_only_tracks():
    folder = PlannedFolder(
        folder_name="MyYT",
        archive_id="yt-id",
        resolved=[
            ResolvedTrack(youtube_video_id="v1", spotify=None),  # YT-only
            ResolvedTrack(youtube_video_id="v2", spotify=_meta()),  # Spotify
        ],
    )
    overrides = folder.info_overrides()
    assert "v1" not in overrides
    assert "v2" in overrides


def test_planned_folder_info_overrides_ignores_bad_release_year():
    folder = PlannedFolder(
        folder_name="Cool",
        archive_id="cool-id",
        resolved=[ResolvedTrack(youtube_video_id="v", spotify=_meta(release_date="bogus"))],
    )
    overrides = folder.info_overrides()
    assert "release_year" not in overrides["v"]


# --- End-to-end: the PlannedFolder → MetadataPP pipeline ---


def test_pipeline_planned_folder_through_metadata_pp():
    folder = PlannedFolder(
        folder_name="Suvepäev",
        archive_id="sp",
        resolved=[ResolvedTrack(
            youtube_video_id="liemvid",
            spotify=_meta(
                title="If Only I Could - Liem Remix",
                artist="Fusion Groove Orchestra, Steve Lucas, Liem",
            ),
        )],
    )
    pp = MetadataPP(overrides=folder.info_overrides())
    info = {"id": "liemvid", "title": "YT garbage", "artist": "Channel"}
    _, out = pp.run(info)
    assert out["title"] == "If Only I Could - Liem Remix"
    assert out["artist"] == "Fusion Groove Orchestra, Steve Lucas, Liem"
