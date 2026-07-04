from pathlib import Path

from yt_playlists.config_loader import load


def _write(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


def test_missing_file_defaults(tmp_path: Path):
    # An absent config is a valid zero-config run: default tag, no YT extras.
    cfg = load(tmp_path / "no.toml")
    assert cfg.spotify_tag == "[DJ]"
    assert cfg.youtube_urls == []


def test_full_config(tmp_path: Path):
    p = _write(
        tmp_path / "p.toml",
        '[sources.spotify]\ntag = "[MIX]"\n[sources.youtube]\nplaylists = ["https://yt/x", "https://yt/y"]\n',
    )
    cfg = load(p)
    assert cfg.spotify_tag == "[MIX]"
    assert cfg.youtube_urls == ["https://yt/x", "https://yt/y"]


def test_defaults_when_missing(tmp_path: Path):
    p = _write(tmp_path / "p.toml", "")
    cfg = load(p)
    assert cfg.spotify_tag == "[DJ]"
    assert cfg.youtube_urls == []


def test_invalid_urls_filtered(tmp_path: Path):
    p = _write(
        tmp_path / "p.toml",
        '[sources.youtube]\nplaylists = ["http://ok", "not-a-url", "https://ok2"]\n',
    )
    cfg = load(p)
    assert cfg.youtube_urls == ["http://ok", "https://ok2"]
