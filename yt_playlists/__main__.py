"""CLI entry point."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from . import config
from .auth.spotify_pkce import AuthError, logout
from .config_loader import load as load_config
from .dashboard import make_dashboard
from .downloader import Downloader
from .match_cache import MatchCache
from .orphan_cleaner import clean_orphans
from .overrides import Overrides
from .pipeline import Pipeline
from .summary import render_discovered, render_final_summary
from .unavailable import UnavailableTracker


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="yt-playlists",
        description="Spotify-first music library downloader with brew-style multi-bar dashboard.",
    )
    p.add_argument("--no-dashboard", action="store_true", help="single-line live summary")
    p.add_argument("--debug", action="store_true", help="verbose yt-dlp to logs/debug.log")
    p.add_argument("--logout", action="store_true", help="delete the cached Spotify token + exit")
    p.add_argument("--clean-orphans", action="store_true", help="empty stale archives + exit")
    return p.parse_args(argv)


def _pick_dashboard_mode(args, *, isatty: bool) -> str:
    if not isatty:
        return "plain"
    if args.no_dashboard:
        return "summary"
    return "bars"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    console = Console(highlight=False)

    if args.logout:
        removed = logout()
        console.print("Spotify token removed." if removed else "No cached Spotify token.")
        return 0

    config.ensure_dirs()

    if args.clean_orphans:
        clean_orphans(console, config.ARCHIVES_DIR, config.OUTPUT_ROOT)
        return 0

    try:
        cfg = load_config()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        return 1

    cache = MatchCache(config.MATCH_CACHE)
    overrides = Overrides(config.OVERRIDES_TOML)

    unavailable = UnavailableTracker(config.UNAVAILABLE_FILE)
    unavailable.reset()
    config.DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.DEBUG_LOG.write_text("", encoding="utf-8")
    config.UNMATCHED_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.UNMATCHED_LOG.write_text("", encoding="utf-8")

    pipeline = Pipeline(
        console=console,
        spotify_tag=cfg.spotify_tag,
        youtube_urls=cfg.youtube_urls,
        cache=cache,
        overrides=overrides,
        resolutions_log=config.RESOLUTIONS_LOG,
        unmatched_log=config.UNMATCHED_LOG,
    )

    try:
        spotify_discovered, youtube_discovered = pipeline.discover()
    except AuthError as e:
        console.print(f"[red]Auth error:[/] {e}")
        return 1

    spotify_resolved = pipeline.resolve_spotify(spotify_discovered)
    folders = pipeline.plan(spotify_resolved, youtube_discovered)
    render_discovered(console, folders)

    if not folders:
        return 0

    mode = _pick_dashboard_mode(args, isatty=sys.stdout.isatty())
    with make_dashboard(console, mode=mode) as dashboard:
        downloader = Downloader(
            archives_dir=config.ARCHIVES_DIR,
            output_root=config.OUTPUT_ROOT,
            dashboard=dashboard,
            unavailable=unavailable,
            debug_log=config.DEBUG_LOG,
            debug=args.debug,
        )
        outcomes = pipeline.download(folders, downloader=downloader)

    render_final_summary(
        console,
        outcomes,
        folders,
        archives_dir=config.ARCHIVES_DIR,
        unavailable=unavailable,
        output_root=config.OUTPUT_ROOT,
        debug_log=config.DEBUG_LOG,
        unmatched_log=config.UNMATCHED_LOG,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
