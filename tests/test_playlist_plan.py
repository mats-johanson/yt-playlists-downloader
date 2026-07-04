from yt_playlists.playlist_plan import plan
from yt_playlists.sources import DiscoveredPlaylist
from yt_playlists.tracks import ResolvedTrack, SpotifyTrackMeta, UnresolvedTrack


def _meta(sid="s1", artist="A", title="T"):
    return SpotifyTrackMeta(
        spotify_id=sid, title=title, artist=artist, album="",
        duration_ms=0, explicit=False, isrc=None, release_date=None,
    )


def _spotify_dpl(folder="Cool", tracks=None):
    return DiscoveredPlaylist(
        folder_name=folder,
        archive_id=f"spotify:{folder}",
        source_label=f"spotify:{folder}",
        tracks=tracks or [],
    )


def _yt_dpl(folder="Cool", video_ids=None):
    tracks = [
        UnresolvedTrack(youtube_video_id=v, youtube_title=v)
        for v in (video_ids or [])
    ]
    return DiscoveredPlaylist(
        folder_name=folder, archive_id=f"youtube:{folder}",
        source_label=f"youtube:{folder}", tracks=tracks,
    )


def test_single_spotify_folder():
    dpl = _spotify_dpl("Cool")
    resolved = [ResolvedTrack(youtube_video_id="v1", spotify=_meta())]
    result = plan([(dpl, resolved, [])], [])
    assert len(result) == 1
    assert result[0].folder_name == "Cool"
    assert len(result[0].resolved) == 1
    assert result[0].merge_note is None


def test_spotify_youtube_merge_with_note():
    sdpl = _spotify_dpl("Cool")
    sresolved = [ResolvedTrack(youtube_video_id="v_spotify", spotify=_meta())]
    ydpl = _yt_dpl("Cool", ["v_youtube"])
    result = plan([(sdpl, sresolved, [])], [ydpl])
    assert len(result) == 1
    folder = result[0]
    assert folder.folder_name == "Cool"
    assert len(folder.resolved) == 2
    assert folder.merge_note is not None
    assert "youtube:Cool" in folder.merge_note


def test_same_video_id_dedup_spotify_wins_metadata():
    # Spotify resolved video X with metadata; YouTube source ALSO contains X.
    # Result: 1 entry for X, carrying Spotify metadata.
    sdpl = _spotify_dpl("Cool")
    sresolved = [ResolvedTrack(youtube_video_id="shared", spotify=_meta())]
    ydpl = _yt_dpl("Cool", ["shared"])
    result = plan([(sdpl, sresolved, [])], [ydpl])
    folder = result[0]
    assert len(folder.resolved) == 1
    assert folder.resolved[0].spotify is not None


def test_different_folders_stay_separate():
    a = _spotify_dpl("Cool")
    b = _spotify_dpl("Deep")
    result = plan(
        [
            (a, [ResolvedTrack(youtube_video_id="va", spotify=_meta("sa"))], []),
            (b, [ResolvedTrack(youtube_video_id="vb", spotify=_meta("sb"))], []),
        ],
        [],
    )
    assert {f.folder_name for f in result} == {"Cool", "Deep"}
    assert all(f.merge_note is None for f in result)
