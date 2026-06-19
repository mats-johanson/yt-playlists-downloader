from pathlib import Path

from yt_playlists.overrides import Overrides


def test_missing_file_returns_none(tmp_path: Path):
    o = Overrides(tmp_path / "no.toml")
    assert o.get("anything") is None


def test_flat_format(tmp_path: Path):
    p = tmp_path / "ov.toml"
    p.write_text('"track1" = "video1"\n"track2" = "video2"\n', encoding="utf-8")
    o = Overrides(p)
    assert o.get("track1") == "video1"
    assert o.get("track2") == "video2"
    assert o.get("track3") is None


def test_tracks_table_format(tmp_path: Path):
    p = tmp_path / "ov.toml"
    p.write_text('[tracks]\n"abc" = "xyz"\n', encoding="utf-8")
    o = Overrides(p)
    assert o.get("abc") == "xyz"
