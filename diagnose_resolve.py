"""Dry-run: discover + resolve + plan; print results; no downloads.

Run via:  uv run python diagnose_resolve.py
"""

import sys

from rich.console import Console

from yt_playlists import config
from yt_playlists.config_loader import load as load_config
from yt_playlists.match_cache import MatchCache
from yt_playlists.overrides import Overrides
from yt_playlists.pipeline import Pipeline


def main() -> int:
    console = Console(highlight=False)
    config.ensure_dirs()

    try:
        cfg = load_config()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        return 1

    # Fresh resolution log + unmatched log for this run.
    config.RESOLUTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.RESOLUTIONS_LOG.write_text("", encoding="utf-8")
    config.UNMATCHED_LOG.write_text("", encoding="utf-8")

    cache = MatchCache(config.MATCH_CACHE)
    overrides = Overrides(config.OVERRIDES_TOML)

    pipeline = Pipeline(
        console=console,
        spotify_tag=cfg.spotify_tag,
        youtube_urls=cfg.youtube_urls,
        cache=cache,
        overrides=overrides,
        resolutions_log=config.RESOLUTIONS_LOG,
        unmatched_log=config.UNMATCHED_LOG,
    )

    spotify_discovered, youtube_discovered = pipeline.discover()
    spotify_resolved = pipeline.resolve_spotify(spotify_discovered)
    folders = pipeline.plan(spotify_resolved, youtube_discovered)

    console.print()
    console.print(f"[bold]Result:[/] {len(folders)} folder(s) planned.")
    for f in folders:
        n_matched = sum(1 for r in f.resolved if r.match_reason and "matched" in r.match_reason)
        n_cache = sum(1 for r in f.resolved if r.match_reason == "cache")
        n_override = sum(1 for r in f.resolved if r.match_reason == "override")
        console.print(
            f"  [bold]{f.folder_name}[/]  resolved={len(f.resolved)} "
            f"(matched={n_matched} cache={n_cache} override={n_override}) "
            f"unmatched={len(f.unmatched)}"
        )
    console.print()
    console.print(f"Detail: {config.RESOLUTIONS_LOG}")
    console.print(f"Unmatched (paste-ready): {config.UNMATCHED_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
