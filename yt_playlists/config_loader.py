"""Read `config/playlists.toml`.

Schema:
  [sources.spotify]
  tag = "[DJ]"

  [sources.youtube]
  playlists = ["https://...", ...]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class PlaylistsConfig:
    spotify_tag: str
    youtube_urls: list[str]


def load(path: Path | None = None) -> PlaylistsConfig:
    path = path or config.PLAYLISTS_TOML
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Copy {path.with_suffix('.toml.example')} "
            f"to {path} and edit."
        )
    with path.open("rb") as f:
        data = tomllib.load(f)

    sources = data.get("sources", {})
    spotify = sources.get("spotify", {}) or {}
    youtube = sources.get("youtube", {}) or {}

    tag = spotify.get("tag", config.DEFAULT_SPOTIFY_TAG)
    if not isinstance(tag, str) or not tag.strip():
        tag = config.DEFAULT_SPOTIFY_TAG

    urls = youtube.get("playlists", []) or []
    if not isinstance(urls, list):
        urls = []
    urls = [u for u in urls if isinstance(u, str) and u.strip().lower().startswith("http")]

    return PlaylistsConfig(spotify_tag=tag, youtube_urls=urls)
