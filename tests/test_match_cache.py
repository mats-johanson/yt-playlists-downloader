from pathlib import Path

from yt_playlists.match_cache import MatchCache
from yt_playlists.tracks import ResolvedTrack, SpotifyTrackMeta


def _meta(spotify_id="abc"):
    return SpotifyTrackMeta(
        spotify_id=spotify_id,
        title="Glue",
        artist="Bicep",
        album="Bicep",
        duration_ms=270_000,
        explicit=False,
        isrc=None,
        release_date="2017-09-01",
    )


def test_get_returns_none_for_missing(tmp_path: Path):
    c = MatchCache(tmp_path / "cache.json")
    assert c.get("never") is None


def test_put_then_get_round_trips_full_snapshot(tmp_path: Path):
    c = MatchCache(tmp_path / "cache.json")
    r = ResolvedTrack(
        youtube_video_id="vid123",
        spotify=_meta("xyz"),
        match_score=88.0,
        match_reason="matched",
    )
    c.put(r)
    out = c.get("xyz")
    assert out is not None
    assert out.youtube_video_id == "vid123"
    assert out.match_score == 88.0
    assert out.spotify is not None
    assert out.spotify.artist == "Bicep"
    assert out.spotify.album == "Bicep"


def test_persisted_across_instances(tmp_path: Path):
    p = tmp_path / "cache.json"
    c1 = MatchCache(p)
    c1.put(ResolvedTrack(youtube_video_id="v1", spotify=_meta("k1")))
    c2 = MatchCache(p)
    assert c2.get("k1") is not None


def test_evict_removes_entry(tmp_path: Path):
    p = tmp_path / "cache.json"
    c = MatchCache(p)
    c.put(ResolvedTrack(youtube_video_id="v1", spotify=_meta("k1")))
    c.evict("k1")
    assert c.get("k1") is None


def test_wrong_schema_version_ignored(tmp_path: Path):
    p = tmp_path / "cache.json"
    p.write_text('{"version": 999, "entries": {"k1": {}}}', encoding="utf-8")
    c = MatchCache(p)
    assert c.get("k1") is None


def test_corrupt_file_falls_back_to_empty(tmp_path: Path):
    p = tmp_path / "cache.json"
    p.write_text("not json {{{", encoding="utf-8")
    c = MatchCache(p)
    assert c.get("anything") is None
