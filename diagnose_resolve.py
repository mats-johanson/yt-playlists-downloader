"""Dry-run: discover + resolve + plan; print results; no downloads.

Writes to logs/{resolutions,unmatched}.diag.{log,txt} so the production
unmatched.txt the user just curated isn't clobbered.

Run via:  uv run python diagnose_resolve.py
"""

import sys

from rich.console import Console

from yt_playlists import config
from yt_playlists.config_loader import load as load_config
from yt_playlists.match_cache import MatchCache
from yt_playlists.overrides import Overrides
from yt_playlists.pipeline import Pipeline
from yt_playlists.unavailable import UnavailableTracker


def main() -> int:
    console = Console(highlight=False)
    config.ensure_dirs()

    cfg = load_config()

    diag_resolutions = config.LOGS_DIR / "resolutions.diag.log"
    diag_unmatched = config.LOGS_DIR / "unmatched.diag.txt"
    diag_resolutions.parent.mkdir(parents=True, exist_ok=True)
    diag_resolutions.write_text("", encoding="utf-8")
    diag_unmatched.write_text("", encoding="utf-8")

    cache = MatchCache(config.MATCH_CACHE)
    overrides = Overrides(config.OVERRIDES_TOML)
    unavailable = UnavailableTracker(config.UNAVAILABLE_FILE)

    pipeline = Pipeline(
        console=console,
        spotify_tag=cfg.spotify_tag,
        youtube_urls=cfg.youtube_urls,
        cache=cache,
        overrides=overrides,
        unavailable=unavailable,
        resolutions_log=diag_resolutions,
        unmatched_log=diag_unmatched,
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
    console.print(f"Detail: {diag_resolutions}")
    console.print(f"Unmatched (paste-ready): {diag_unmatched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
