from yt_playlists.matcher import (
    YtCandidate,
    artist_similarity,
    build_search_query,
    forbidden_penalty,
    resolve,
    score,
    strip_for_search,
    title_similarity,
)
from yt_playlists.tracks import ResolvedTrack, SpotifyTrackMeta, Unmatched


def _track(**kw):
    base = dict(
        spotify_id="abc",
        title="Glue",
        artist="Bicep",
        album="Bicep",
        duration_ms=270_000,
        explicit=False,
        isrc=None,
        release_date=None,
    )
    base.update(kw)
    return SpotifyTrackMeta(**base)


def test_strip_for_search_drops_parentheticals_and_dash_suffix():
    assert strip_for_search("Some Song (Remastered 2019)") == "Some Song"
    assert strip_for_search("Title - 2019 Mix") == "Title"
    assert strip_for_search("Plain Title") == "Plain Title"


def test_build_search_query_uses_stripped_title():
    t = _track(title="Some Song (Remastered)")
    assert build_search_query(t) == "Bicep Some Song"


def test_artist_similarity_exact():
    t = _track()
    c = YtCandidate(video_id="x", title="Glue (Official Audio)", uploader="Bicep", duration_s=270)
    assert artist_similarity(t, c) > 0.0


def test_title_similarity_handles_accents():
    t = _track(title="Déjà Vu")
    c = YtCandidate(video_id="x", title="deja vu official audio", uploader="X", duration_s=200)
    assert title_similarity(t, c) > 0.3


def test_forbidden_penalty_hits_live_when_studio():
    t = _track(title="Glue")
    c = YtCandidate(video_id="x", title="Bicep Glue Live at Boiler Room", uploader="Boiler Room", duration_s=270)
    p = forbidden_penalty(t, c)
    assert p > 0


def test_forbidden_penalty_skips_live_when_already_in_track():
    t = _track(title="Glue (Live)")
    c = YtCandidate(video_id="x", title="Bicep Glue (Live at Boiler Room)", uploader="Boiler Room", duration_s=270)
    p = forbidden_penalty(t, c)
    assert p == 0


def test_score_picks_higher_artist_match():
    t = _track()
    cands = [
        YtCandidate(video_id="wrong", title="Glue Cover by John", uploader="John", duration_s=270),
        YtCandidate(video_id="right", title="Bicep - Glue", uploader="BicepVEVO", duration_s=270),
    ]
    best, _ = score(t, cands)
    assert best is not None
    assert best.candidate.video_id == "right"


def test_score_rejects_when_no_artist_match():
    t = _track()
    cands = [
        YtCandidate(video_id="w1", title="Random Song", uploader="Random", duration_s=270),
    ]
    best, _ = score(t, cands)
    assert best is None


def test_resolve_uses_fixture_search_fn():
    t = _track()
    def fake_search(query, n):
        assert "Bicep" in query and "Glue" in query
        return [
            YtCandidate(video_id="right", title="Bicep - Glue", uploader="BicepVEVO", duration_s=270),
        ]
    result = resolve(t, fake_search)
    assert isinstance(result, ResolvedTrack)
    assert result.youtube_video_id == "right"
    assert result.spotify is t


def test_resolve_returns_unmatched_when_no_candidates():
    t = _track()
    result = resolve(t, lambda q, n: [])
    assert isinstance(result, Unmatched)
    assert result.best_candidate_video_id is None
