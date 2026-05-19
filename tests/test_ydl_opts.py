"""Structural assertions on the yt-dlp options dict.

Can't run ffmpeg in unit tests, but the postprocessor order is load-bearing
(EmbedThumbnail MUST run after FFmpegExtractAudio; MetadataParser MUST run
pre_process so the parsed artist field reaches both tagging and the filename
template). These tests catch reorder regressions.
"""

from pathlib import Path
from unittest.mock import MagicMock

from yt_playlists.downloader import _ydl_opts


def _opts() -> dict:
    return _ydl_opts(
        archive=Path("/tmp/archive.txt"),
        out_tmpl="/tmp/out/%(title)s.%(ext)s",
        logger=MagicMock(),
        progress_hook=lambda _d: None,
        debug=False,
    )


def test_postprocessor_order_is_extract_parse_metadata_embed():
    keys = [pp["key"] for pp in _opts()["postprocessors"]]
    assert keys == [
        "FFmpegExtractAudio",
        "MetadataFromField",
        "FFmpegMetadata",
        "EmbedThumbnail",
    ]


def test_extract_audio_targets_mp3_v0():
    extract = _opts()["postprocessors"][0]
    assert extract["preferredcodec"] == "mp3"
    assert extract["preferredquality"] == "0"


def test_metadata_from_field_parses_artist_title_from_title():
    parser = _opts()["postprocessors"][1]
    assert parser["formats"] == [
        r"title:^(?P<artist>.+?) - (?P<title>.+)$",
    ]


def test_ffmpeg_metadata_writes_tags_but_no_chapters():
    md = _opts()["postprocessors"][2]
    assert md["add_metadata"] is True
    assert md["add_chapters"] is False


def test_embed_thumbnail_removes_sidecar():
    embed = _opts()["postprocessors"][3]
    assert embed["already_have_thumbnail"] is False


def test_writethumbnail_is_on():
    # EmbedThumbnail needs the sidecar to exist before it can embed it.
    assert _opts()["writethumbnail"] is True


def test_no_album_mapping():
    # Playlists are mood collections, not albums — must NOT map playlist_title → album.
    parser = _opts()["postprocessors"][1]
    formats_str = repr(parser["formats"])
    assert "album" not in formats_str
    assert "playlist_title" not in formats_str
