from pathlib import Path

from yt_playlists.downloader import _next_available_name


def test_returns_original_when_free(tmp_path: Path):
    target = tmp_path / "song.mp3"
    assert _next_available_name(target) == target


def test_suffixes_when_taken(tmp_path: Path):
    target = tmp_path / "song.mp3"
    target.write_bytes(b"")
    assert _next_available_name(target) == tmp_path / "song (2).mp3"


def test_increments_until_free(tmp_path: Path):
    (tmp_path / "song.mp3").write_bytes(b"")
    (tmp_path / "song (2).mp3").write_bytes(b"")
    (tmp_path / "song (3).mp3").write_bytes(b"")
    assert _next_available_name(tmp_path / "song.mp3") == tmp_path / "song (4).mp3"
